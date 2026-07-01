# Engine Backend Problem Audit

**Date:** 2026-07-01 · **Scope:** engine/backend only (no UI) across three repos — Macro Dashboard (`engine/`, ~122K LOC, 404 files), Mastermind bot (~725K LOC), charting-app Terminal (`signal_layer`/`indicator_engine`).

**Method:** 22 purpose-built probes (one per engine cluster × lens), each finding adversarially re-verified against the real code, 4 completeness critics, then deduped + ranked synthesis. **134 confirmed problems → 46 distinct, in 8 themes.** Five of the most load-bearing claims were independently spot-verified by the orchestrating session (netliq units bug, axis renormalization, dead bot ML parquets, stale Terminal confluence fork, quad leg composition) — all confirmed.

**Companion doc:** `research/ENGINE_FIX_MASTERPLAN.md` — solution architecture, phasing, and delegation map for fixing everything below.

**Sequencing (which diseases poison the others):**
1. Fix measurement first (Theme C + leakage half of A/D) — every "does engine X have edge?" question is unanswerable while the validation frame leaks.
2. Establish sources of truth (A + F) — until regime/signal concepts have one canonical answer, confluence is a coincidence of divergent formulas.
3. Close the loops (E) and wire the orphans (H) — but only after (1), or the loops learn the wrong thing.
4. Then individual predictive-power kills (B) and sizing-discipline fixes (G) become tractable.

---

## Themes

### T1. No single regime source of truth

The most consequential engine in the stack — the macro regime that tilts every allocation and (via the bot) caps real gross — is simultaneously (a) a coincident market-momentum relabel branded as a forward Hedgeye Quad, (b) computed on look-ahead-contaminated econ inputs (reference-date stamping, revised finals, full-sample HMM smoothing), and (c) forked into 5+ region engines and 3 risk-vocabulary generations that disagree with no arbiter. The single question 'what regime are we in and how risk-off should we be?' has no canonical answer.

- Canonical US Quad is a coincident market-momentum relabel branded as a forward Hedgeye regime
- Monthly FRED prints enter the daily axis on reference-month not release date — systematic look-ahead in every historical regime row
- Quad classifier runs on revised FRED finals; point-in-time vintage path exists but is bounded to M2SL and never wired in
- Three generations of 'how risk-off' (MRS / risk_state / risk_radar) run at once; the oldest, documented-failed engine still drives the sector conviction gate while the fixes are cosmetic-only
- Five region quad engines and coincident-vs-forward reads share the 'Quad' label but measure incomparable axes with no reconciliation
- P(Quad) HMM ships live with full-sample non-causal smoothing while its calibration lane never runs
- us2y_direction stays in the growth axis as a sign-ambiguous rate leg the upgrade plan flagged for removal

### T2. Predictive claims with no validated forward edge

A large family of decision- or display-facing signals assert forward predictive power that has never been measured, was measured on the wrong (survivorship/optimistic/proxy) sample, or is contradicted by the system's own scorecard. These are the signals a real-money trader is most likely to over-trust because they wear a 'validated' badge.

- Forward base-effect / HMM regime suite is display-only with empty grading ledgers and no gate script that was supposed to license it
- Equity/EDGAR factor composite has negative measured IC yet ranks leaderboards and leaks as a board tiebreaker at equal weight
- Convergence alt-data tiers cite a track record with zero scored entries; the highest-weighted channel (insider_cluster) uses a construction the IC harness never blessed
- Real-activity / radar divergence overlay reorders the live allocation book with zero matured validation and fires high-severity alerts
- Crowding and clean-entry basket gates are live weight/entry signals the engine's own calibration grades as non-predictive or gate-rejected
- Dispersion regime gross dial swings real position size ±20-60% on hand-picked terciles with no measured edge, and grosses UP into high-VIX stress
- CA/INTL name-score is skewed ±20% by an admitted-unvalidated momentum prior; tier weights and _REGIME_W impose orderings the base rates don't support
- BTC master blends extremes-only signals as continuous contributions; the 1064/364 cycle clock and anti-predictive OI leg drive alert-level flags on n=3 in-sample cycles
- GEX dealer-gamma sign is an unobservable assumption that gives SPY/SPX opposite regimes and makes single-name regimes constant, feeding the vol-shock predictor's heaviest factor

### T3. Backtests you can't trust

The validation infrastructure that is supposed to keep the suite honest is either measuring a contaminated quantity, running on a survivor-only / total-return / same-bar-fill panel, or built-but-never-called. Every 'held-out stop-out rate' and drawdown-improvement headline inherits these biases, and the anti-overfit governance that would catch them is orphaned.

- Impulse-radar falsifier label window is mis-windowed (includes past+current bar, 1 day forward), inflating the only gate that keeps BTC act-tier legs live
- Anti-overfit governance capstone (promotion_gate + drift + walk_forward + holdout_vault) is fully orphaned — no signal is ever gated by it and no registry exists
- Trial ledger has 20 entries with zero declared budgets, making multiple-testing deflation near-inert across ~25 harnesses
- Deep-history and forward track-record backtests run on today's surviving, dividend-adjusted, same-bar-fill panel with no survivorship or next-bar correction
- Tier weights and freshness/CN-blend constants are anecdote-picked or 2.5x-spread on ~5pp measured evidence, never re-swept on a fresh universe
- signal_lab scorecard and anticipation GO-gate are frozen hand-quoted constants with no freshness marker — a decayed signal shows its original DSR forever
- Provisional partial-bar repaint: freshest tier badges are computed on an incomplete resample bucket the validation never saw

### T4. Data feeds that fail silently

A single class of bug repeated everywhere: when a feed dies or lags, the engine renormalizes over survivors, forward-fills stale bytes, or reads a fresh build date — and keeps publishing a confident label with no flag. Because the bot consumes these artifacts for real gross decisions and no repo asserts input freshness across the boundary, a data-plumbing outage can silently degrade the regime into pure price momentum or even flip the quad and trigger a portfolio rebuild.

- Dead/half-open FRED breaker silently degrades the macro regime into a price-momentum proxy with unchanged confidence and label
- Quality gate and bot tripwire both miss feed staleness — a total FRED outage passes with n_failed=0 and the bot's only check reads an always-fresh build date (block flag defaults OFF)
- A FRED outage can spuriously flip the quad via axis renormalization and trigger a real-money bot portfolio rebuild
- Every cross-repo handoff (bot macro_risk, risk_sizing, conviction, intel bridge, autonomous) reads dashboard/vendor JSON with no staleness guard — missing file defaults to full risk
- Regime history strips per-component freshness columns, making degraded (price-only) days unauditable in every walk-forward
- EBP and other slow legs silently exit composites on publication lag with no cadence-aware staleness gate or consumer-facing flag

### T5. Learning loops that don't learn

Every accountability and self-calibration mechanism the suite advertises — desk track records, committee calibration, reputation weighting, lens gate, attribution — is either subtract-only, structurally starved of samples, wired to nothing, or grades a quantity collinear with its own input. Grades are computed and then discarded from every deterministic step. The system is trusted as if it self-corrects when it runs permanently open-loop.

- Outcome ledgers grade every desk but results never re-weight any deterministic decision — the loop closes only inside the LLM context window
- Committee/calibration runs fully open-loop (all multipliers 1.0, zero resolved theses) with no surfaced 'uncalibrated' warning; reputation and self-mirror are flag-gated OFF with no activation criterion
- Reputation/attribution damper is subtract-only AND sign-inverted for veto seats — correct SENTINEL/Gate vetoes would accumulate negative bps; attribution.persist has zero callers
- Self-calibrating lens gate and per-channel convergence weights are structurally starved — min-n can never be cleared, so size authority stays equal-vote forever
- No aggregate calibration of combined_score / research_score — the traded ranking and the buy gate rest on assumed additivity with no forward Brier check
- Radar / altdata / stock_desk accountability ledgers have thousands of snapshots but zero graded outcomes; radar_scorer isn't even called by the nightly build
- Calibration Hub / desk cards display conviction badges with n=0 measured basis on non-calibration pages

### T6. Cross-system signal divergence

The dashboard, the bot, and the Terminal each independently re-derive the same concepts — risk state, credit impulse, VIX term structure, net liquidity, per-stock direction, confluence signals — from overlapping-but-differently-stale inputs with different formulas and vocabularies, and only cosmetic labels (never the decision-driving numbers) are reconciled. Three systems can show three contradictory reads on the same ticker or the same macro day with no arbiter.

- Bot re-derives macro risk_on/caution/risk_off independently, ignoring the dashboard's published risk_state verdict; 3-state vs 5-state with no mapping and risk_brain.json has no consumer
- Terminal confluence.py is a stale fork (resample 3B + wrong RMA/EMA warm-up) emitting materially different BUY/SELL signals than the dashboard chart the user trades
- golden_gate parity harness certifies engines against the stale Terminal oracle and self-checks the oracle against itself — it rejects correct engines and blesses the bug
- Intel bridge fabricates BULL from ladder.dir alone on names the dashboard rates Neutral/Hold, emitting a self-contradictory dir+score to the copilot
- Same concept computed 2-3x with divergent formulas and no source of truth: credit impulse, VIX term structure, net Fed liquidity
- risk_state / risk_radar emit independent gross_factor multipliers with different band maps; only the label is reconciled, never the magnitude, and the directive has zero in-repo consumers
- No feedback loop: bot realized P&L never adjusts dashboard engine weights or thresholds; the handoff is strictly one-way

### T7. Sizing and gating logic that silently defeats its own discipline

The risk-management and gating machinery contains structural defects that quietly undo the very discipline it advertises: initial-size cash is renormalized back to full budget, correlation is discarded so a correlated book sizes as if independent, cap overflow leaks to cash, the research gate can't reject a sized name, doctrine vetoes fire as advisory flags, and the entire fast-derisk defense stack is flag-gated OFF.

- Research gate is structurally incapable of rejecting a sized name on the 91%-of-the-time deterministic path — pure confluence rubber stamp with the confirm bar below the floor every sized name reaches
- Macro-risk / fast-derisk / risk-officer defense stack built after the 2026-06-23 crash is flag-gated OFF and absent from .env — the identical failure mode is unmitigated in production
- risk_sizing renormalizes the conviction book back to full budget, erasing the initial-size discipline cash so unconfirmed names deploy at full weight
- Position sizing is inverse-vol only — avg_corr is in the snapshot but discarded, so a correlated AI-buildout book sizes as if independent (the 06-23 concentration cause)
- Doctrine detectors D1/D2/D4 specified as hard sizing vetoes fire only as advisory flags; cap clamps leak budget to cash with no redistribution
- Committee model diversity is illusory — FORGE and SENTINEL both resolve to Opus on the default path, and the re-digest confirm pass grades its own bull thesis
- Autonomous ungated-Opus book runs on schedule and is risk-blind by default while the disciplined flagship seats default OFF
- Confluence-gate double-counts: both engine_score and research_score are monotone in the same confluence variable, inflating combined conviction and size

### T8. Orphaned and dead decision code

A striking number of complete, tested engines — including validated risk dials and safety layers — have zero production callers, are wired to non-existent files, or fire on structurally unreachable paths. Because each degrades gracefully and never errors, 'building' is indistinguishable from 'broken', and the appearance of an operational safety/learning layer masks that it never runs.

- ML/prediction stack (predictions, student, distill, shadow risk_tilt) is a silent no-op — reads _closes_deep/_closes_delisted parquets that don't exist, 6,677 ledger rows 0 resolved
- net_exposure — the only IC/OOS-validated drawdown dial (halves MaxDD) — is fully orphaned with zero non-test callers
- spvector LLM knife-veto is structurally unreachable (on_stress_day never passed); 202 log rows, 0 vetoes, shock_reversible always 'unknown'
- heavyweight_outcomes accountability engine is orphaned with a false docstring claiming a call site that doesn't exist
- panel.adjudicate is a dead second adjudicator imported but never called, risking a future contradictory de-escalation path
- LLM synthesis/veto calls set no temperature or seed, so every graded lean and any future wired veto (catalyst_tone shock_reversible) is a coin-flip run-to-run

---

## The 46 problems (ranked by severity × real-money impact × confidence)

### #1. Canonical US Quad is a coincident market-momentum relabel branded as a forward Hedgeye regime — and it drives real bot gross

`dashboard + bot` · `predictive-power` · **severity: critical** · confidence: high

**Evidence:** axes.py:39-51 + config.yml: market-proxy legs (copper_gold, xly_xlp, iwm_spy, cyc_def, breadth) sum 5.5 vs econ legs (payrolls, indpro, wei, gdpnow) 2.0 = 73% market-proxy; every leg is score_from_z(slope_z(...)), a 20d first-derivative coincident read. base_effect.py:5-8 names the gap explicitly. Quad feeds run.py:84 latest['quad'], playbook exposure_dial/scenario_odds, and brain/macro_risk.py:_collect reading regime fields binds judgment_book.py:294-300 gross_cap/add-permission when MASTERMIND_MACRO_RISK armed. No forward-IC validation of the scored quad exists (scripts/calibrate_regime.py is the BTC harness).

**Why it matters:** The single most consequential signal in the whole stack. A Q4 flip largely confirms a drawdown already underway from the SPY/breadth/copper-gold it is derived from; it cannot lead the market it re-encodes. Users are told they hold a forward Hedgeye Quad and the bot caps real gross on it — both act on a coincident momentum relabel wearing a forward badge.

**Why it's hard / why unfixed:** Market proxies are the only daily-frequency signals; removing them leaves a monthly laggy econ axis. The honest forward engine (base_effect) is correctly gated on a validator that doesn't exist and needs months of accrual plus ALFRED PIT vintages for core CPI/PCE that aren't in the store. The 'markets lead, econ confirms' defense is a prior, not an IC measurement.

**Deep-reasoning brief:** Core tension: a daily-frequency, decision-driving regime label must be either genuinely forward or honestly branded as coincident — right now it is coincident but sold as forward. Attack: design a probabilistic regime read that (a) separates the forward-predictive component from the coincident momentum re-encoding, (b) quantifies how much true lead-time (if any) survives once the market-proxy legs are down-weighted, and (c) exposes a calibrated confidence that degrades honestly when only coincident legs are live. A novel solution must let a real-money consumer distinguish 'the world is turning' from 'prices already turned', without inventing daily econ data that doesn't exist.

### #2. Research gate is a pure confluence rubber stamp on the 91%-of-the-time deterministic path — cannot reject any name it sizes, and the fast-derisk defense stack is flag-gated OFF

`bot` · `engine-correctness` · **severity: critical** · confidence: high

**Evidence:** research_paper.py: engine_score=50+confluence*50, _deterministic_score=50+confluence*40+small lens deltas, combined=0.5*each ≈ 50+confluence*45; CONFIRM_THRESHOLD=60 so any confluence≳0.222 passes with empty rows, and conviction.py:195 only sizes confluence>0.30 — every sized name auto-passes. 93/102 saved papers are mode='engine' (deterministic path); LLM failure silently falls back with no flag. research_score is never fed to the Brier/calibration ledger (DOCTRINE A7 unmet). Separately, _macro_risk_enabled/derisk.enabled/risk_officer all default '0' and are absent from .env, so macro_risk.apply_risk_state, fragility_chain, defensive_playbook, and intraday de-risk (all built after the 2026-06-23 crash) are inert on live paper money.

**Why it matters:** The user understands every buy to pass a deep armed-Claude research report; in production it is a confluence anchor 91% of the time with the confirm bar set below the floor any sized name reaches, and the gate's verdict is never bound to a forward outcome so it can rubber-stamp indefinitely undetected. Meanwhile the exact 06-23 concentration failure mode is completely unmitigated in the default config.

**Why it's hard / why unfixed:** The rubber stamp is hidden because research_score reads lens deltas that look independent but are tiny (+/-3..16) bolted on a confluence anchor; unit tests feed synthetic lens rows so CI never sees the empty-row degeneration. The defense flags default OFF for byte-identical reproducibility and because the deterministic risk_state classifier's precision was never measured, so turning them on risks churning the book.

**Deep-reasoning brief:** Core tension: a gate whose two 'independent' scores are both monotone functions of the same confluence input adds zero rejection power, and a defense system that only works when a human sets undocumented env vars protects nothing. Attack: design a research/confirmation gate that provably adds signal orthogonal to confluence (and can reject a sized name), and a risk-defense arming criterion tied to a measured false-trigger rate so the 06-23 protections can be safely default-ON. A novel solution must make 'the gate confirmed this buy' and 'the book de-grossed' falsifiable and self-activating, not aspirational flags.

### #3. Feeds fail silently: dead/half-open FRED degrades the regime into pure price momentum with unchanged label, and no gate or bot tripwire catches it

`dashboard + bot` · `data-accuracy` · **severity: critical** · confidence: high

**Evidence:** run_status FRED circuit_breaker=6; PAYEMS/INDPRO last 2026-05-01 (61d, past 60d ffill); axes.py:79 renormalizes wsum over non-NaN legs so expired FRED legs vanish silently; axes.py:87 min_components=3 is trivially met by 6 price legs. macro_audit.json fred n_failed=0 (staleness is soft-flag only); collect.py aborts only at fail_pct>5%. Bot: macro_refresh.is_stale reads an always-fresh site build date (site rebuilds daily off price data); MACRO_STALE_BLOCK defaults OFF; brain/macro_risk.py:86-92 missing-file → risk_on (gross_cap=1.0). A quad flip via renormalization triggers brain/gate.py state_change → full portfolio rebuild.

**Why it matters:** A pure data-plumbing outage (FRED WAF — a documented recurring pattern) can silently strip the regime's fundamental confirmers, publish an unchanged confident 'Goldilocks' label, pass every quality gate, and either be traded on as a full macro read or spuriously flip the quad and cause a real-money portfolio rebuild — a trade caused by an outage, not the market.

**Why it's hard / why unfixed:** Degradation is architecturally invisible: renormalization is a robustness feature, staleness is deliberately non-fatal to avoid false aborts on legitimately-slow prints (ECI quarterly, GDPNow sporadic), and the freshness signal the bot needs (per-feed breaker state + series last_date) is never published in the handoff artifacts. The engine can't tell 'the world changed' from 'my inputs disappeared' — both are a score move after renormalization.

**Deep-reasoning brief:** Core tension: graceful degradation and silent degradation are the same code path, and the one system that trades real money reads a freshness proxy that can never go stale. Attack: design a cadence-aware, cross-repo input-freshness contract that (a) distinguishes an intentionally-forward-filled slow series from a dead feed, (b) demotes regime confidence / vetoes quad transitions when load-bearing legs are stale rather than genuinely NaN, and (c) publishes machine-readable per-leg freshness the bot can hard-gate on. A novel solution must prevent an outage from ever masquerading as a confident regime read or causing an outage-driven rebuild.

### #4. Three generations of 'how risk-off' run at once; the documented-failed oldest engine still drives the real sizing gate while the fixes are cosmetic-only, and the bot re-derives a fourth

`dashboard + bot` · `confluence-gap` · **severity: critical** · confidence: high

**Evidence:** Same-repo triplet: conditions.macro_risk_score (MRS), risk_state.py (5-band, gross {caution:0.90..risk_off:0.60}) whose docstring says it exists because MRS stayed green into the 2026-06-23 SMH -7% peak, and risk_radar.py (labeled MRS's 'successor'). sector_central.py:98-135 computes the conviction gate_factor from MRS and explicitly states it IGNORES the Risk Radar — only the headline string was patched so pages 'never disagree' cosmetically. risk_state.directives (gross_factor/favor_entries/cap_leadership) has zero code consumers. Bot: brain/macro_risk.py:426 re-derives its own risk_on/caution/risk_off (3-state, _risk_off_score=0.60) from raw JSONs, never reading regime['risk_state'] (5-state); risk_brain.json has no bot consumer; etf_board adds a fifth 'calm/elevated/stressed' band.

**Why it matters:** On a repeat of 2026-06-23 the banner can scream Risk-off (radar) while the conviction gate still sizes as Risk-on (MRS), and the money-moving bot can independently conclude a contradictory state and cap the book — the correction to the exact documented failure was cosmetic, not behavioral, and there is no single source of truth for the gross response across four coexisting risk vocabularies.

**Why it's hard / why unfixed:** Retiring MRS from gate_factor means re-deriving and re-backtesting the sector conviction gate against engines with different scales, band cut points, and partly-unvalidated gross curves; MRS is wired into many other consumers. The bot deliberately keeps a self-contained deterministic risk core, so honoring the dashboard's gross_factor means giving up independence-by-design. Everything degrades to None and never asserts agreement.

**Deep-reasoning brief:** Core tension: four risk engines built for different consumers with intentionally different thresholds, where the one that actually shrinks real-money conviction is the one proven to fail at its job. Attack: design a canonical risk-response abstraction that (a) lets specialized engines contribute without the label and the sizing magnitude diverging, (b) makes the decision-binding gross number traceable to a single reconciled verdict, and (c) resolves the 3-vs-5-state cross-repo vocabulary without silently collapsing the granularity that catches positioning blow-offs. A novel solution must guarantee the number that sizes the book and the number the user sees can never contradict on a stress day.

### #5. Monthly FRED prints enter the daily axis on reference-month not release date — a ~2-6 week look-ahead in every historical row of the growth/inflation axes

`dashboard` · `data-accuracy` · **severity: critical** · confidence: high

**Evidence:** inputs.py:61-71 put() reindexes each FRED series onto the daily grid at its native (reference-month) index and only forward-fills — never shifts by publication lag, despite comments acknowledging INDPRO 'published ~6 weeks' late (L132-133). Consumers: axes.py:47-48 monthly_sign('payrolls'/'indpro'); axes.py:60 sticky_cpi_direction via inputs.py:191 rolling(63) on reference-stamped sticky_cpi. Contrast regime.py:107 which DOES .shift(lag_bd) for WALCL. collectors/fred.py:42-59 already builds an ALFRED vintage matrix with true realtime_start dates for exactly these series — the fix data exists in data/fred_vintage/vintages.parquet and is entirely unused by the daily-axis path.

**Why it matters:** Every historical row of the growth/inflation axes 'knows' a monthly print weeks before it published, so ANY backtest, IC, or track-record on the daily axis frame is contaminated with forward information — directly inflating the apparent skill of the exact forward-regime claims the suite is built on. Distinct from the revision-magnitude items: this is availability-timing look-ahead, present even for never-revised prints.

**Why it's hard / why unfixed:** Fixing requires joining every monthly series against its ALFRED realtime_start, stamping on release date (revision-aware if you want the initial value), then re-fitting axis thresholds/z-baselines calibrated on the leaked frame. Invisible on the live last-row read (roughly correct for daily-collected data) and only corrupts the historical validation span, so it never shows in site output. The vintage store was scoped as a separate PIT lane never wired back into build_features.

**Deep-reasoning brief:** Core tension: the validation history that certifies the regime is the exact frame with the look-ahead baked in, and the point-in-time data that would fix it is collected but unused. Attack: design a release-date-stamped, revision-aware point-in-time axis frame that (a) uses the existing ALFRED vintage matrix, (b) re-baselines the axis z-scores and thresholds on the de-leaked history, and (c) quantifies how much of the regime's 'validated edge' survives once the timing leak is removed. A novel solution must produce a backtest a real-money trader can trust as genuinely as-of.

### #6. Impulse-radar falsifier label window is mis-windowed (includes past+current bar, only 1 day forward), inflating the only gate that keeps BTC act-tier legs live

`dashboard` · `backtest-rigor` · **severity: critical** · confidence: high

**Evidence:** btc_impulse_radar_backtest.py:50 fwd_min = close.shift(-1).rolling(LABEL_H).min() — at row t this uses close[t-1], close[t], close[t+1] (window t-1..t+1), not the claimed (t, t+3]; it includes the prior and signal bars and reaches only 1 day forward. The u1 trigger fires on a same-day down move so the label directly overlaps the trigger. impulse_legs_gate.json shows all three legs 'leading' with lifts from this contaminated label (d2 4.368, d3 2.677, u1 6.394); u1's holdout is only 14 fires. This gate demotes/keeps ACT-TIER legs; the CI honesty check tests against the same contaminated metric.

**Why it matters:** This is the only gate that keeps BTC de-risk/act legs live. Inflated lifts mean legs that should be demoted stay 'leading' and keep awarding act-tier points to live de-risk/act calls a trader may act on, and the non-zero-exit CI guarantee is hollow because it validates against the contamination.

**Why it's hard / why unfixed:** The one-liner shift(-1).rolling(H) reads plausibly as a forward window and the module is framed as a rigorous leak-free falsifier, so reviewers trust it. Fixing changes headline lifts and may demote legs treated as validated for months; adding a per-leg minimum-n floor (u1 has 14) compounds the demotion.

**Deep-reasoning brief:** Core tension: a rigor-branded falsifier whose own label leaks the answer, so its 'proof' is circular. Attack: re-derive a strictly-forward, trigger-disjoint labeling scheme and re-establish which BTC impulse legs survive on clean labels with adequate n; design a gate whose CI honesty check can't be satisfied by the contamination it's meant to catch. A novel solution must give a real-money BTC de-risk trader legs whose lift is measured on returns the signal could not have seen.

### #7. Terminal confluence.py is a stale fork emitting materially different BUY/SELL signals than the dashboard chart the user trades — and the parity gate blesses the bug

`cross-system` · `engine-correctness` · **severity: critical** · confidence: high

**Evidence:** charting-app/signal_layer/confluence.py:58-59,65,106 still uses ewm(alpha=1/n, adjust=True) RMA, ewm(span) EMA without adjust=False, and resample('3B').last() — all three replaced in the dashboard oracle (_rma SMA-seeded, ema via adjust=False, session-grouped _resample_3d), whose docstrings state the old paths are WRONG ('3B mis-splits sessions, moved ~80% of signal dates on NVDA'; 'adjust=True flips near-threshold crosses'). The file still claims to be a 'VERBATIM' copy. golden_gate.py:43 defaults engine_fn to the oracle itself so Phase-0b self-check trivially passes (diff 0); the harness only compares OTHER engines to this stale reference, so a correct PineTS engine would FAIL and a bug-reproducing one PASSES. contracts.py maps these signals to BUY/SELL/REBUY/CUT consumed by the Mastermind brain.

**Why it matters:** The Terminal emits materially different entry/exit signals for the same symbol than the dashboard chart the user trades against on real money (~80% of signal dates relocated), and the 'trust layer' that is supposed to prove TradingView parity actively rejects correct engines and hard-codes the errors into every downstream indicator the brain consumes.

**Why it's hard / why unfixed:** The two files live in separate repos with no shared package or CI parity test; the golden_gate harness compares everything TO the stale reference so it cannot detect that the reference itself drifted. Detection requires cross-repo diffing no automation performs.

**Deep-reasoning brief:** Core tension: a parity gate anchored to a known-wrong oracle inverts its own purpose. Attack: design a cross-repo signal-parity contract where the reference is the corrected math (or an external TradingView ground truth), such that a stale fork FAILS and a correct engine PASSES; make the Terminal and dashboard provably emit identical BUY/SELL for the same symbol/date. A novel solution must close the divergence a real-money trader is currently exposed to and make the trust layer catch reference drift, not enforce it.

### #8. ML/prediction stack is a silent no-op reading files that don't exist — 6,677 ledger rows, 0 resolved, all 'fast-arm' calibration seats permanently cold

`bot` · `engine-correctness` · **severity: critical** · confidence: high

**Evidence:** predictions._load_panel reads vendor/macro/data/breadth/_closes_deep.parquet and _closes_delisted.parquet — neither exists (only _closes_cache and friends); returns None silently via bare except. ledger.jsonl has 6,677 rows, 0 resolved (all status='open'), including fully-matured entries. The 'if panel and spy is not None' guard never fires so nothing is labeled; student/distill _dataset short-circuit on None (metrics.json {status:'building', n:0}, no model.cbm); calibration universe_strategist/pm/timing stay n=0/multiplier=1.0. shadow_books risk_tilt also degrades to unscaled weights on the same None panel. The intended survivorship-safe deep+delisted panel documented in predictions.py:18-21 was never vendored.

**Why it matters:** Three forward-accruing foundation engines (universe prediction scorecard, CatBoost student that flag-gates into Opus prompts, distilled-Opus router) plus the risk_tilt A/B have produced zero output since inception and structurally cannot until filenames are fixed. Dashboards show 'building' (implying time will mature them), masking that they are broken by a wrong path — and the whole designed 'sample unlock' (hundreds of graded cross-sectional predictions/month) never starts, so calibration stays cold from scratch.

**Why it's hard / why unfixed:** Every consumer is degrade-safe by design (returns []/'building'/never raises) so nothing errors or alerts; 'building' is indistinguishable from genuinely accumulating. The files are gitignored large outputs of a macro-repo build step the bot expects pre-vendored — a cross-repo lifecycle gap with no contract check, and fixing the filename without also fixing adjustment/PIT semantics would surface a second latent leak.

**Deep-reasoning brief:** Core tension: a degrade-safe architecture makes 'broken' and 'building' identical, so a dead ML foundation looks operational for months. Attack: design a cross-repo data-contract + liveness check that asserts the panel exists, is survivorship-safe and point-in-time correct, and that resolutions actually accrue — turning silent None into a loud, actionable failure. A novel solution must make the sample-unlock loop verifiably alive before any decision (student prompt_line, distill router) is allowed to trust it.

### #9. Bot reads every dashboard/vendor handoff with no staleness guard; the offline one-way pipeline means stale bytes silently size real positions

`cross-system` · `data-accuracy` · **severity: high** · confidence: high

**Evidence:** portfolio/lenses.py:24, strategist.py:48, reputation.py:82, risk_sizing.py:27-32, conviction.py:31-36, autonomous.py:465-472 all json.loads(read_text()) with only 'if exists' — no mtime/as_of/generated_at comparison, though the files DO carry as_of (us_standouts.json as_of 2026-06-30). macro_refresh.is_stale reads the always-fresh site build date not the price-panel date; MACRO_STALE_BLOCK defaults OFF. feed_health returns 'snapshot' (never 'down') for US so US books are never gated. vendor/macro is a symlink to a tree that may not have re-rendered (render ~67min, CPU-bound, GitHub runners can't push to local bot).

**Why it matters:** The single most important macro input to an autonomous real-money book has zero freshness detection: a stale or half-written regime/standouts file from a failed render is consumed as truth and drives gross caps, sector tilts, and candidate universe with no alarm. On a weekend or after a CI failure the bot silently trades on stale data.

**Why it's hard / why unfixed:** The handoff is intentionally one-way and offline (no shared clock across isolated repos), and fail-open was chosen to avoid halting the book on benign lag (holidays, closed markets where 'old' is correct). Distinguishing benign lag from a genuinely stale mount requires a per-artifact expected-cadence contract spanning two repos.

**Deep-reasoning brief:** Core tension: an autonomous real-money book that fail-opens on stale inputs, where 'unchanged because markets closed' and 'unchanged because the pipeline broke' look identical. Attack: design a cross-repo as-of freshness contract with per-artifact cadence expectations that lets the bot safely fail-closed on genuine staleness without halting on benign lag. A novel solution must give the bot a reliable, self-arming staleness veto on the specific inputs that size the book.

### #10. Anti-overfit governance capstone (promotion_gate + drift + walk_forward + holdout_vault) is fully orphaned — no signal is ever gated, no registry exists, and net_exposure (the one validated drawdown dial) is also uncalled

`dashboard` · `backtest-rigor` · **severity: high** · confidence: high

**Evidence:** promotion_gate.py composes DSR + PBO/CSCV + CPCV + PageHinkley/ADWIN drift + holdout-vault into the promote-eligible verdict but is referenced only by tests; no signal_registry / shadow→canary→live state machine exists (find *registry* returns only the admin experiments tracker). walk_forward.py is imported by nothing in engine/scripts and no wf_*.json logs exist; drift.rolling_ic_drift never runs on a live IC stream. Separately, net_exposure.py (validated: Sharpe 0.42→0.58, MaxDD -86%→-52%, zero selection alpha, per validate_timing_overlay.py) has zero non-test callers — books run without the drawdown dial its own backtest measured.

**Why it matters:** The apparatus meant to STOP overfit signals reaching live sizing never runs, so every signal (dispersion dial, composite legs, anticipation gate, china anti-chase leg) is promoted by hand with no Deflated-Sharpe/PBO/drift check enforced at deploy, and decaying legs rot silently. Simultaneously a validated dial that roughly halves max drawdown is shipped and never turned on — the drawdown protection its backtest proved is absent from production.

**Why it's hard / why unfixed:** Component statistics are individually built and tested, creating the appearance of a working stack; the missing piece is the boring orchestration + registry state machine and the per-leg rolling-IC / trial-budget streams that are sparse or absent (same starvation as the bot lens gate). Orphaned validated engines are invisible: CI is green, nothing errors, books just run at higher net exposure than the validated policy allows.

**Deep-reasoning brief:** Core tension: a fully-built anti-overfit and drawdown-protection layer that gates nothing and sizes nothing, so its existence provides false comfort. Attack: design the promotion state machine and per-leg rolling-IC/trial-budget feeds that let promotion_gate actually gate real signals, and a safe path to wire net_exposure's validated drawdown dial into live sizing. A novel solution must convert built-but-inert governance into an enforced propose→gate→promote pipeline where a decaying or unvalidated leg cannot reach real money.

### #11. Committee/calibration runs fully open-loop with illusory model diversity: all multipliers 1.0, zero resolved theses, FORGE and SENTINEL both resolve to Opus, and reputation/self-mirror are flag-gated OFF with no activation criterion

`bot` · `confluence-gap` · **severity: high** · confidence: high

**Evidence:** calibration.json: every agent n=0, reliability=null, multiplier=1.0, status='building'; outcome_ledger.jsonl has 1 governance row; theses.jsonl 42 theses 0 resolved (first cohort matures ~2026-07-17). committee.py:108-113 applies calibration only to sentinel (multiplier 1.0 no-op). config/agents.yml maps both pm:opus and deep:opus so FORGE and SENTINEL are the same model on the default cli path (client.py TIERS distinguishes them only on the secondary API path). reputation.py:62-65 (MASTERMIND_REPUTATION_WEIGHTING) and self_mirror.py:40-41 (MASTERMIND_SELF_MIRROR) default '0' with no arming condition; reputation is the ONLY path to above-1.0 influence.

**Why it matters:** The headline 'self-calibrating adversarial committee' applies zero adjustment and its adversary is the same model with the same blind spots — when the model misjudges a crowded AI theme, SENTINEL is wrong in the same direction, silently failing to catch precisely the errors it exists for. Calibration can only ever shrink overconfident seats; a reliably-right seat earns no upsizing because reputation/self-mirror stay off indefinitely with no monitor.

**Why it's hard / why unfixed:** Genuine chicken-and-egg (MIN_N=12 resolved per bucket, first cohort mid-July) means the loop can't close today; true lens diversity needs a different architecture/vendor, not just input isolation; and the fail-safe OFF defaults have no code-defined arming criterion, so the compounding half of the loop stays dark unless a human watches calibration.json and sets env vars.

**Deep-reasoning brief:** Core tension: an adversarial committee whose adversary shares the primary's weights, running open-loop with no self-arming and only-shrink calibration. Attack: design (a) genuine lens diversity that doesn't collapse to one model's priors, (b) a measurable test that SENTINEL's OPPOSE is actually independent of FORGE's confidence, and (c) an auto-arming calibration/reputation loop with a defined activation criterion so reliable seats earn influence. A novel solution must make the committee demonstrably catch errors the primary alone would miss, and surface an 'uncalibrated / same-model' warning at the decision layer until it does.

### #12. Bot re-derives macro risk independently and never reads the dashboard verdict; same concept (credit impulse, VIX term, net liquidity) computed 2-3x across engines with divergent formulas and no source of truth

`cross-system` · `confluence-gap` · **severity: high** · confidence: high

**Evidence:** brain/macro_risk.py:120,426-464 re-fuses raw component JSONs into its own 3-state risk (never reads regime['risk_state']/regime['macro_risk']). Credit impulse: china_strategies.py:70-71 uses a 2nd-derivative (diff of YoY) feeding leveraged GTAA books, while china_radar.py:74-75 uses a 1st-derivative under the same label. VIX term: vol_regime ts_slope from raw series vs vol_shock_scorecard _f_vix_term from vol_sentiment cache (3 different cached copies). Net Fed liquidity computed 3 ways: inputs.py:279 canonical (3-term, bn, drives regime overlay), forex_dollar.py:231 (drops TGA, inverts sign), anticipation.py:103 (drops TGA, mis-scales WALCL 1000x). No shared helper; divergences can flip sign on the same day.

**Why it matters:** The number that de-grosses real books and the number the user sees can disagree with no reconciliation, and the confluence narrative the dashboard sells (multiple engines 'agreeing') is undermined because the same-named quantity is a mathematically different series on the decision surface vs the display surface — routinely disagreeing in sign at turning points where it matters most.

**Why it's hard / why unfixed:** Each engine re-derives inline from raw parquets rather than importing a canonical helper, so divergence is invisible without diffing call sites; each formula is individually defensible (level vs acceleration, TGA in/out, sign convention), and only the decision-path variant ever gets scrutiny so display-only forks never triggered a validation pass forcing one source of truth. The bot's independence-by-design conflicts with honoring the dashboard verdict.

**Deep-reasoning brief:** Core tension: 'confluence' is asserted across engines that secretly compute the same concept differently, and the money-moving bot is blind to the display verdict. Attack: design canonical single-source definitions (credit impulse, VIX term structure, net liquidity, risk state) with one shared helper and an as-of contract, plus a reconciliation layer so any surface reading a concept reads the same series — or explicitly declares which basis it uses. A novel solution must make cross-engine 'agreement' real rather than a coincidence of divergent formulas, and let the bot consume (or deliberately override, with logging) the dashboard's verdict instead of silently re-deriving a contradictory one.

### #13. Outcome ledgers grade every desk/signal but results never re-weight any deterministic decision — the loop closes only inside the LLM context window

`cross-system` · `confluence-gap` · **severity: high** · confidence: high

**Evidence:** desk_scorer.py:26 'CONTEXT-ONLY — track_record never enters a score/size/allocation'; master_brain injects desk_track_records into the LLM prompt only. No code feeds hit-rates back into signal_gate weights, tier weights, or any deterministic ranking; a 30%-hit desk keeps full influence. Bot side: attribution.persist has zero callers (rollup permanently {}), reputation damper inert; combined_score / research_score never regressed on forward outcomes (no Brier). The dashboard's forward loggers grade in isolation and the bot's realized P&L never writes back to dashboard weights (handoff strictly one-way).

**Why it matters:** Grades are computed, logged, and discarded from every downstream arithmetic step; a cold or wrong desk keeps its full weight in the synthesis indefinitely, the traded ranking rests on assumed additivity no one has measured, and the one system with real (paper) outcomes cannot correct the system generating the signals — miscalibrated signals persist forever.

**Why it's hard / why unfixed:** Closed-loop re-weighting needs PIT-clean samples (many desks n<10) and risks overfitting tiny samples; the 'context-only' rail is a deliberate safety choice; outcome attribution back to a specific engine is genuinely hard (many engines feed one trade); and building the loop requires a shared signal-id/outcome contract that exists nowhere in either codebase.

**Deep-reasoning brief:** Core tension: a suite full of accountability ledgers where measurement never touches the arithmetic that trades. Attack: design a deterministic, overfitting-resistant re-weighting mechanism (and the shared signal-id→outcome contract to feed it) that lets validated hit-rates and realized P&L actually move desk weights, tier weights, and combined_score — without the small-sample instability that motivated the context-only firewall. A novel solution must let a reliably-wrong desk lose real influence and a reliably-right one gain it, closing the loop in the numbers, not just the prompt.

### #14. Quad classifier and axes run on revised FRED finals; the point-in-time vintage path exists but is bounded to M2SL and never wired into the canonical path

`dashboard` · `data-accuracy` · **severity: critical** · confidence: high

**Evidence:** inputs.py:28-34,134-135 reads payrolls/indpro/CPI from the latest-revision store; axes.py:47-48 consumes them; regime.py classify() has zero references to vintages/as_of/realtime. The ALFRED path (collectors/fred.py fetch_vintages, base_effect._level) is consumed only by calibrate_regime.py which itself states it is 'Bounded to M2SL' and degrades gracefully if absent. DECISIONS.md calls the payrolls/INDPRO vintage gap 'REMAINING (narrow, separate, NOT done)'. run.py calls base_effect.compute() with no as_of/vintages so even its PIT path falls back to finals (revised=True flagged). Post-2008 payrolls were revised ~558k lower — the historical growth axis 'knew' the true trend before the market.

**Why it matters:** Distinct from the reference-vs-release timing leak: this is the revision-magnitude leak. The split-half validation that certifies the quad's edge was run on revised finals, so the historical axis is smoother and more prescient than what was knowable in real time — flattering the validated edge and producing potentially different quad signals at turning points than were available live, on the regime that gates real bot gross.

**Why it's hard / why unfixed:** Threading as_of through the full axis/regime stack and re-running split-half validation on PIT data may weaken the published IC; the ALFRED matrix has ~1 row per period so walk-forward needs careful as_of interpolation; doing it partially (some legs PIT, some revised) is arguably worse than the current consistent-but-biased approach. Machinery exists but is deliberately not wired to the canonical path.

**Deep-reasoning brief:** Core tension: the regime's edge was validated on data no trader had at the time, and the PIT fix may reveal the edge is smaller. Attack: thread revision-aware as-of vintages through the axis/regime stack and re-run the split-half validation honestly, quantifying how much edge survives; design an approach that avoids the partial-PIT hazard (mixing vintaged and revised legs). A novel solution must tell a real-money trader how much of the quad's certified edge is real vs a revision artifact.

### #15. Deep-history and forward track-records run on today's surviving, dividend-adjusted, same-bar-fill panel with no survivorship or next-bar correction — inflating every 'validated' drawdown headline

`dashboard` · `backtest-rigor` · **severity: high** · confidence: high

**Evidence:** universe_history.as_of_members exists but no backtest engine imports it (sector_signals.py:416, validation.py, china_validation.py all use the present-day panel). track_record.py:228 sets entry_price at the signal bar (same-bar fill) vs validation.py:70 which correctly does alloc.shift(1) 'act next bar'; sector_signals.py:426 and meta_label.py:135 mirror the same-bar denominator. All stores are auto_adjust=True total-return (name_score_grader iloc[h] positional not h trading days; desk grading resolves from the current-membership _closes_cache so delisted names silently drop out — survivorship in the accountability loop itself). The forward record parquet is gitignored and marker-file-driven (dropped names stop maturing). The '-23.7%→-15.5% drawdown' improvement claim rests on all of this.

**Why it matters:** Every 'held-out' hit-rate, rank-IC, and drawdown-improvement headline is optimistic: dead/delisted names are erased (flattering crisis breadth and desk hit-rates), same-bar fills flatter short mean-reversion signals most, total-return credits soften troughs, and the honesty-gate grader that decides 'validated vs experimental' is itself biased. A trader over-sizes a mechanical system whose per-trade edge is overstated in exactly the direction that hurts.

**Why it's hard / why unfixed:** No free point-in-time membership feed exists for CN/HK/US pre-accrual; the store carries adjusted close only (next-open fill uncomputable for many names without an OHLC feed); the biases are documented as accepted for the 'measurement-only' logger but leak into sector_signals/meta_label/desks which ARE surfaced as validated. A genuine fix needs a paid historical-constituents + unadjusted price source.

**Deep-reasoning brief:** Core tension: the suite's proof-of-edge artifacts are built on the cheapest data path (survivors, total-return, same-bar), so the honesty gate is itself dishonest. Attack: design a validation panel and grading convention that is survivorship-aware, uses next-bar/next-open fills, and separates price-return from total-return — or, where free data forbids that, a principled correction/haircut that bounds the optimism a real-money trader should discount. A novel solution must make the drawdown-improvement claim survive an as-of, next-bar, delisting-aware re-test.

### #16. Forward base-effect / HMM regime suite is a shipped forecasting engine whose forecasts have never been scored — empty ledgers, missing gate script, PIT path bypassed

`dashboard` · `predictive-power` · **severity: high** · confidence: high

**Evidence:** run.py marks base_effect and regime_hmm DISPLAY-ONLY 'until scripts/validate_regime_fwd.py clears it' — that validator does not exist anywhere in the repo. base_effect_fwd.jsonl has exactly 1 row (2026-06-30) with realized_growth_2d_at_63d and realized_infl_2d_at_63d both null. run.py:149 calls base_effect.compute() with no as_of/vintages so its PIT path falls back to finals. regime_hmm.py:24-27 is full-sample non-causal smoothed (historical points use future data); the calibration lane that should write hmm_latest.json never runs and the file doesn't exist. ALFRED core CPI/PCE vintages needed for a leak-free inflation validation are absent from the store.

**Why it matters:** A prominently-shipped 'forward regime / base-effect acceleration' program presents a forward quad forecast to users, but its self-grading ledger is empty (63+ bdays to mature one row), the gate script licensing it to drive decisions was never written, and its historical P(Quad) chart is look-ahead-contaminated by smoothing — the canonical unvalidated-predictive-claim failure mode on the flagship overhaul.

**Why it's hard / why unfixed:** Forward validation is intrinsically slow (one row/session, 63 bdays); the inflation-axis leak-free test needs ALFRED core-inflation vintages that don't exist; a causal expanding-window HMM refit reopens covariance-singularity/thin-quad and label-switching problems; and because it's cleanly quarantined as zero-weight there is no operational pressure to finish the gate.

**Deep-reasoning brief:** Core tension: a forecasting engine whose forecasts have never been graded, gated on a validator that was never written, displaying a smoothed hindsight chart as if forward. Attack: design the forward-grading protocol and go/no-go gate (including a causal, non-smoothed P(Quad) and a leak-free inflation-axis test that works despite missing core-CPI/PCE vintages) that could actually promote base-effect from display to decision. A novel solution must give a defensible accrual path and honest interim uncertainty so the forward-regime thesis can be proven or killed rather than shipped indefinitely unvalidated.

### #17. Reputation/attribution safety damper is subtract-only AND sign-inverted for veto seats — correct SENTINEL/Gate vetoes would accumulate negative bps and get their influence floored

`bot` · `engine-correctness` · **severity: high** · confidence: high

**Evidence:** attribution.py:220 seat_bps = shares[s]*rel_bps uniformly; for a SENTINEL OPPOSE / Gate WITHHOLD on a name that then falls (rel_bps<0) the seat receives NEGATIVE attribution though it was correct, and _shares() gives the dominant de-risking seat a +30% bump so a correct veto on a 500-bps loser yields ~150 bps negative. No sign inversion anywhere (grep for sign/invert/negate/*-1 empty). reputation.py:190-208 grades outcome=1 for a correct veto but reputation.py:290-292 then floors influence to W_FLOOR when cumulative attributed bps<0 — penalizing the exact seats that saved the book. Both attribution.persist and the reputation flag are off, masking the combined path; no test exercises it.

**Why it matters:** If persist + reputation were enabled (their intended state), the seats whose sole function is avoiding losers (SENTINEL, Risk Officer, Gate) would be systematically punished for being right — the opposite of the intended safety damper — while calibration simultaneously credits them, pulling the same seats in opposite directions.

**Why it's hard / why unfixed:** Brinson attribution is intuitive for additive selection/allocation but silently wrong for subtract-only seats: the credit for a veto is the AVOIDED loss (sign-inverted vs the position's realized return), which uniform share*rel_bps cannot express. The bug looks mathematically correct in isolation and is masked today because both the persist call and the reputation flag are off.

**Deep-reasoning brief:** Core tension: a P&L-attribution framework designed for buyers, applied to seats whose value is what they prevent. Attack: design an attribution scheme that correctly credits avoided losses to veto/de-risk seats (so being right about a faller earns positive, not negative, reputation) and reconcile it with the calibration outcome so the two graders agree in sign. A novel solution must make the safety damper actually reward the seats that protect a real-money book, before the loop is ever armed.

### #18. Intel bridge fabricates BULL from ladder.dir alone on names the dashboard rates Neutral/Hold, and serves stale snapshots as current with no freshness gate

`cross-system` · `confluence-gap` · **severity: high** · confidence: high

**Evidence:** ingest/pull_macro_intel.py:80-94: if ladder_dir=='up' → ai_dir='BULL' with no reference to conviction.verdict/entry_signal.status/decision.band. Verified on A.json (asof 2026-06-26): ladder.dir='up' → emits ai_lean.dir='BULL' while conviction.verdict='Neutral', score=50, entry_signal.status='hold', decision.band='neutral' — the emitted object is internally contradictory (dir='BULL', score=50). Same file copies src asof through with no max-age check (A.json 5 days stale); hardcoded absolute MACRO_STOCKDATA path breaks in worktrees; pull_macro_intel is wired into neither refresh.sh nor terminal-refresh.sh (manual-only). tape.ai_lean is rendered in the Terminal panel and exposed to the LLM copilot via get_intel.

**Why it matters:** The Terminal manufactures a BULL conviction on a name the flagship per-stock brain explicitly declined to call directional, feeds a self-contradictory dir+score to both the user and the copilot on real-money decisions, and — because it is manual-only and un-gated — silently serves days-old GEX/conviction/analyst numbers as live with no staleness banner.

**Why it's hard / why unfixed:** The dashboard's composite verdict is spread across several i18n/region fields; the bridge reached for the single easiest scalar (ladder.dir) and there is no shared contract enforcing terminal dir == dashboard band, so divergence is invisible until diffed field-by-field. Freshness is a cross-repo property needing each source's cadence + current date; the hardcoded absolute path makes a stale file look like 'no file'.

**Deep-reasoning brief:** Core tension: a bridge that reduces a rich multi-field verdict to one scalar produces a directional call the source system explicitly refused to make, with no freshness or consistency contract. Attack: design a bridge contract where the Terminal's directional lean must be derivable from (and consistent with) the dashboard's composite decision band, and a cross-repo freshness gate that refuses to serve stale intel as live. A novel solution must guarantee the copilot and user never see a BULL the dashboard would call Neutral, nor a days-old snapshot presented as current.

### #19. Self-calibrating lens gate and per-channel convergence weights are structurally starved — min-n can never be cleared, so size authority and channel weights stay hand-set forever

`bot + dashboard` · `confluence-gap` · **severity: high** · confidence: high

**Evidence:** lenses.py:935-949 needs outcome_ledger.lens_weights() with min_n=20 graded reads per lens; outcome_ledger.jsonl has 1 non-scoreable row; signal_history covers only a few dozen names/day starting ~2026-06-21, so clearing one lens needs ~4-6 weeks of sustained overlap and possibly never given thin coverage — synthesize() falls to equal-vote 1.0 weights meanwhile. Dashboard mirror: altdata_ledger grades only the aggregate thesis (single rel_return on subject), never by_channel, so the 33 CHANNEL_WEIGHTS (insider_cluster=1.00…retail_buzz=0.15) are permanently uncorrectable; the IC-validated construction (net_usd_mcap|SN) is research-only while production insider_cluster fires on a raw buyer count the IC harness never tested.

**Why it matters:** The gates advertised as self-teaching (lens weights, convergence channel weights) cannot accrue the evidence to move any weight — the size-authority gate stays a static equal-vote model and the highest-weighted alt-data channels stay guesses regardless of which lenses/channels actually predict. Structural starvation reads identically to normal cold-start, so 'building' never resolves and no alarm fires.

**Why it's hard / why unfixed:** The join is fragile across append-only logs with different start dates and universes; per-channel attribution needs isolated single-channel theses (destroying the 'convergence' framing) or a cross-sectional per-channel IC panel that was never wired; and no monitor asserts coverage is broad enough to ever clear min-n. The validated insider construction needs PIT market caps and sector demeaning the live path deliberately avoids.

**Deep-reasoning brief:** Core tension: learning gates that require more graded samples than their own data-collection design can ever produce, so 'adaptive' is aspirational. Attack: design a ledger/attribution structure that can actually accrue per-lens and per-channel forward evidence at the bot's cadence (or a principled prior-shrinkage that degrades gracefully), plus a monitor that distinguishes structural starvation from normal cold-start. A novel solution must make the size-authority and channel weights genuinely correctable — or honestly admit and surface that they are static priors, not earned weights.

### #20. Dispersion regime gross dial swings real position size ±20-60% on hand-picked terciles with no measured edge, and grosses UP into high-VIX stress the sizing layer claims to fade

`dashboard` · `predictive-power` · **severity: high** · confidence: high

**Evidence:** dispersion.py:20-21 hardcodes terciles 0.66/0.33 and _GROSS {lean_in:1.20, neutral:1.0, lean_out:0.75}; consumed as a DECISION lever at build_stock_library.py:1339 → risk_sizing.py:55 size_mult=clip(inv_vol*regime_gross,0,3.0), the final multiplier all four US/CN/HK/CA books apply. No validation (ls *dispersion* empty); docstring cites academic literature for DIRECTION only, never magnitude. Internal contradiction: dispersion.py:8-9 notes high dispersion is 'often high-VIX' and sets lean_in gross=1.20 (grossing UP) while risk_sizing.py:12-15 says the book should 'de-gross in stress'. Related: CA/INTL name-score edge_mult (±20%, 'unvalidated' momentum prior) and subsector _REGIME_W / tier weights impose orderings the base rates don't support.

**Why it matters:** A 1.6x swing in gross across four real-money stock books driven by hand-picked constants presented as if measured, that can gross the book UP into exactly the high-VIX stress the sizing layer is supposed to fade — if the effect is weaker or sign-flipped on this small survivor universe, the dial adds noise to sizing in the most dangerous direction.

**Why it's hard / why unfixed:** Validating a dispersion-conditioned selection-IR edge needs a survivorship-clean cross-sectional book backtest the ~3yr surviving universe can't cleanly provide (easy to overfit) — presumably why the authors leaned on literature, but they then shipped specific fitted-looking constants as if measured, and the up-gross-in-stress sign question is genuinely regime-dependent.

**Deep-reasoning brief:** Core tension: a real-money gross dial with hand-picked magnitudes and an internally contradictory sign (gross up into the stress the book should fade). Attack: measure whether dispersion state actually conditions selection-IR on this universe, resolve the up-vs-down-gross-in-high-VIX sign conflict against the de-gross-in-stress mandate, and replace fitted-looking-but-unmeasured constants with either validated magnitudes or an honest display-only demotion. A novel solution must ensure a sizing lever swinging real capital 1.6x is either measured or not decision-binding, and never grosses into a blow-off.

### #21. Trial ledger has 20 entries with zero declared budgets across ~25 harnesses — multiple-testing deflation is near-inert, so lucky best-of-many configs pass gates they should fail

`dashboard` · `backtest-rigor` · **severity: high** · confidence: high

**Evidence:** data/trial_ledger.jsonl has exactly 20 entries across 5 families, none carrying declared_budget. calibration_hub surfaces this as 'the P3 keystone: honest multiple-testing counts made visible', yet walk_forward.py _mt_bump uses n_trials defaulting to 1 not sourced from the ledger, and signal_lab headlines the S&P vector DSR 0.9994 'at n_trials=30' as a hardcoded REGISTRY constant. ~25 *_phase0/validate_* harnesses each sweep many configs; no automated pass enforces that new harnesses register their budgets.

**Why it matters:** Every deflated-Sharpe / kill-rule / FDR verdict is only honest if the trial count reflects the true specifications searched; with a hand-curated 20 and no budgets, effective deflation is ~zero and lucky configs pass. This underpins the credibility of the entire 'validated' tier.

**Why it's hard / why unfixed:** Counting the true multiple-testing budget across 404 engine files and ~25 harnesses is intractable exactly (every parameter tried in development is a trial); the declared_budget mechanism approximates it with an honest upper bound but is entirely unpopulated, and no pass enforces registration.

**Deep-reasoning brief:** Core tension: multiple-testing correction that is only as honest as a trial count nobody maintains. Attack: design a low-friction, hard-to-evade trial-budget accounting (enforced at harness-registration time) that produces a defensible upper-bound n_trials feeding every DSR/kill/FDR gate. A novel solution must make it cheaper for a researcher to register a trial than to skip it, so the deflation a real-money trader relies on reflects the true search space.

### #22. Provisional partial-bar repaint: freshest tier badges are computed on an incomplete resample bucket, plus not-topped veto drops fresh names on one noisy bar — the board's freshest tier is not the tier that was validated

`dashboard` · `data-accuracy` · **severity: high** · confidence: high

**Evidence:** confluence_tiers.py:78-81 _tf_bars resample('2B'/'3B').last().dropna() keeps the last bucket even when only 1-2 of the days printed; signal_quality.py:87 same for the 3D master; FRESH_TICKS=2 specifically surfaces names crossing on this provisional bar and all _xup crosses are iloc[last] on it. The not-topped veto (185-190) reads k3n<d3n from iloc[last] only, so a 1-bar oscillator wiggle on the partial tail silently returns blank (no tier). TIERED_CASCADE held-out stop-out rates and the §7 reclaim validation were run on completed daily bars only — never on the provisional-tail version.

**Why it matters:** A name shown as fresh T1/T2 BUY today can un-cross tomorrow when the bucket completes, and a genuinely fresh name can be silently dropped by one noisy oscillator reading — the same name can appear, vanish, and reappear across daily builds. Point-in-time backtests recompute on completed bars and never see these fires, so the board's freshest, most-acted-on tier is precisely the one the validation didn't cover.

**Why it's hard / why unfixed:** Dropping the incomplete tail delays every legitimately-fresh signal by 2-3 trading days, directly conflicting with the 'about to / just crossed' value prop; the .shift(1) leak-prevention operates within the resampled grid so reviewers assume tail-repaint is covered when it isn't; and the single-bar veto is intentional as an overbought guard (AMAT case), making persistence a real precision/recall tradeoff.

**Deep-reasoning brief:** Core tension: the freshest, most-traded tier is computed on a bar that may not exist tomorrow, and the validation never tested that state. Attack: design a freshness/tier scheme that either validates on the same provisional-tail basis it displays, or delivers 'just-crossed' value without repainting — and a not-topped veto robust to single-bar noise without re-admitting genuinely topped names. A novel solution must make the tier a trader acts on today the same tier that was backtested, and stop the appear/vanish/reappear churn.

### #23. Convergence alt-data tiers and radar/real-activity overlays are live decision surfaces citing track records with zero scored entries, dominated by correlated soft channels

`dashboard` · `predictive-power` · **severity: high** · confidence: high

**Evidence:** altdata track_record.json scored_total=0, open=120, overall.hit_rate=null (HORIZON 63d, earliest 2026-06-19 — no maturity before ~Sep 2026), yet altdata_signals.py:159-163 emits 'weight by that track record' TODAY and the high/medium/low tier is live. Of 120 theses, special_situation appears in 73, material_8k 27, trump 21 — dominated by soft, mutually-correlated same-event channels; convergence_score treats distinct-channel count as independent evidence, and 'high' tier fires on trump_linked+any one channel. Radar/real-activity: radar_ic.json n_matured=0 over 2,216 snapshots; theme_validation val_upgrade (threshold 0.75, uncalibrated) reorders the live N_HOLD allocation slot and fires high-severity 'entered_book' alerts (rank-IC ~0). 13F channel snapshots 92-day-old positions at today's price with no staleness gate.

**Why it matters:** Multiple live, user- and brain-facing decision surfaces (convergence tiers, allocation slot order, alert-center severity) assert or reorder on forward edge that provably doesn't exist yet, the track-record caveat resolves to 'weight by nothing', the tier is a hand-set prior masquerading as earned, and the co-firing structure means the record — when it matures — will measure soft-channel correlation not the hard convergence the design sells.

**Why it's hard / why unfixed:** 63-trading-day horizons on ledgers started days ago cannot mature for months and no historical backtest was run at creation; per-channel/per-theme attribution needs isolated theses or cross-sectional IC panels the lumped ledger can't provide; the soft event flags have no clean history to estimate co-firing; and 'soft demote / one-slot upgrade' framing makes unvalidated live reorders read as prudent rather than as bets.

**Deep-reasoning brief:** Core tension: tiers and allocation nudges shipped ahead of any evidence, with independence assumed among channels that co-fire on the same event. Attack: design a convergence/divergence scoring that (a) penalizes correlated same-event channels instead of counting them as independent, (b) is honest that its tier is a prior until the ledger matures (with an accrual-aware confidence), and (c) can attribute outcomes per channel/theme so the weights become correctable. A novel solution must stop a single corporate event minting a multi-channel 'high' tier and stop an ungraded z-score reordering a real-money book, without waiting months for maturity to say anything at all.

### #24. risk_sizing renormalizes the conviction book back to full budget (erasing initial-size discipline cash) and is inverse-vol only — avg_corr is in the snapshot but discarded, so a correlated book sizes as if independent

`bot` · `engine-correctness` · **severity: high** · confidence: high

**Evidence:** conviction.py:270-272 applies a 0.7 initial-size discount and size_stage='initial', then risk_sizing.py:87-96 renormalizes raw[p]/tot*target so the sum hits budget*selection_gross regardless of the 0.7 discount (pure renormalization when vol_mult=1.0) — unconfirmed names deploy at full budget share while still labeled 'initial'. No covariance/correlation term anywhere (grep correl/cov/kelly = 0); us_standouts.json dispersion_regime carries avg_corr:0.17 but risk_sizing.py:67 extracts only gross_mult and discards it, even though vendor/macro_src implements book_forecast_vol_ann with equicorrelation and is never called. name_cap/sector-cap clamps leak excess to cash with no water-filling redistribution.

**Why it matters:** The catalyst/confirmation gate ('initial vs full size') becomes cosmetic — deliberately-held discipline cash is spent on names the engine flagged as not-yet-confirmed — and a book of correlated AI-buildout names each gets full inverse-vol size as if independent, so realized book vol/beta exceeds target. This is the structural cause of the 06-23 concentration the whole defense stack was built to remedy.

**Why it's hard / why unfixed:** Two sizing passes each independently renormalize to budget (the second added as 'additive, never breaks' on the assumption it only re-weights relatively), so the discipline-erasure is invisible unless you trace that renormalization undoes absolute-weight discipline; correlation-aware sizing needs a PIT pairwise covariance the bot doesn't compute (only a scalar avg_corr), and correct cap redistribution needs an iterative water-filling loop a single-pass min() hides.

**Deep-reasoning brief:** Core tension: a sizer that advertises staged-confirmation discipline and risk-parity but renormalizes the discipline away and ignores correlation entirely. Attack: design a sizing pass that preserves absolute initial-size discipline through renormalization, incorporates the available avg_corr (equicorrelation or better) so a correlated book de-grosses, and redistributes cap overflow via water-filling instead of leaking to cash — while staying robust when the macro fields are absent. A novel solution must make the book's realized vol/beta match target and keep unconfirmed names genuinely under-sized on real money.

### #25. Equity/EDGAR factor composites carry negative measured IC yet rank leaderboards and leak as board tiebreakers at equal weight, including FDR-failing and negative-IC legs

`dashboard` · `predictive-power` · **severity: high** · confidence: high

**Evidence:** ic_scorecard.json: composite ic_ir=-0.049/mean_ic=-0.0072, hit=0.45, survives_fdr=False; investment (-0.036) and low_vol (-0.093) outright negative; only payout survives BH-FDR. equity_factors.py:431-435 builds the composite as a blind equal-weight mean and emits composite_top/bottom rendered in factors.html; setups.py:233-245 and composite_score.py use factor_z / a 'revisions' leg (documented near-useless) as ranking/tiebreak keys for the Top-setups board where users size real trades. compute_factors never consults the scorecard to drop or down-weight losing legs; the scorecard was documented as 'wired to nothing'.

**Why it matters:** The composite leaderboard and the board tiebreak rank names in a marginally anti-predictive direction, dragged by negative-IC legs at full weight, and the Fundamental-Law 'stacking works' argument is invalid because legs aren't checked for positive standalone IC — so board order (a real-money decision surface) can flip on a null/negative leg while the decorrelation check gives false comfort.

**Why it's hard / why unfixed:** Academic priors make equal-weight feel defensible; the scorecard is survivorship-optimistic so even negative ICs are an upper bound; fixing requires IC/FDR-weighting or dropping legs, which needs a view on trustworthy sample periods and a leak-free survivorship-corrected panel the free-data pipeline can't cleanly produce; and the 'context/display' label understates that board rank is itself a decision.

**Deep-reasoning brief:** Core tension: a composite whose own honest scorecard says it's anti-predictive is used to order a real-money board, and the decorrelation check masks that individual legs are negative. Attack: design a composite that respects each leg's measured sign/magnitude (drop or IC-weight FDR-failers) and enforce that the board-ranking path cannot consume a leg the scorecard rejects, given only a survivorship-optimistic panel. A novel solution must ensure the ordering a trader sizes off has non-negative expected edge, not equal-weighted noise.

### #26. Entry-gauge confluence gate is missing on China/HK/CA analyzers though sig_verdict is already computed — 'Buy zone open' shows while the validated confluence cross has not fired

`dashboard` · `confluence-gap` · **severity: high** · confidence: high

**Evidence:** entry_signal.py:128-169 gates buy_now/partial → await_confluence only when buyable=False is passed; build_stock_library.py:1356 passes it for US, but build_china_library.py:872, build_hk_library.py:690, build_canada_library.py:498 all call assess() with NO buyable arg despite computing sig_verdict per-name (china:789, hk:676, ca:455). intl doesn't call entry_signal at all. The assess() docstring rationalizes buyable=None as 'backward compatible', masking that these callers DO compute the confluence.

**Why it matters:** China/HK/CA single-stock pages — the most-used non-US surfaces where the user trades real money — can display 'Buy zone — entry open now' driven purely by the daily-cycle ladder while the validated MACD-2D×StochRSI-3D cross has not fired, and the entry card can contradict the tier badge on the same card (no T1/T2/T3 yet gauge says open).

**Why it's hard / why unfixed:** Looks like one-line plumbing but each market uses different close-series variable names, high is None on CA/CN, and sig_verdict is keyed differently per loop; the docstring frames None as intentional backward-compat so the omission reads as a design choice rather than a bug.

**Deep-reasoning brief:** Core tension: a validated confluence gate exists and is computed, but is silently not threaded into the exact non-US surfaces the user trades most, so the entry card and the tier badge can disagree. Attack: design a market-agnostic entry contract that guarantees the buy-zone gauge and the confluence tier are always derived from the same fired/not-fired state across US/CN/HK/CA/INTL, tolerant of the per-market plumbing differences. A novel solution must make 'entry open now' impossible unless the validated cross has actually fired.

### #27. TSF credit-impulse look-ahead front-runs the ~10-day publication lag, inflating the largest-weight leg de-risking leveraged China GTAA books

`dashboard` · `data-accuracy` · **severity: high** · confidence: high

**Evidence:** collectors/china_credit.py:76 stamps TSF at reference-month start (2026-04-01 for April); china_masterminds.py:88 _LAG_CREDIT=22 trading days → ~May 4, but April TSF publishes ~May 13-15 (collector's own stale_after_days=70 notes '~6-week lag'). The backtest 'knows' the impulse ~10 days before release; same shift in china_strategies._sc_credit_vol/_sc_credit_margin. The credit leg carries 0.45 weight within the regime block which is 0.40 of the whole China book (leveraged 1.3x-1.8x).

**Why it matters:** A systematic ~10-day forward peek at China's most market-moving macro print inflates the credit leg's timing edge in every scorecard/OOS panel that real-money leveraged allocation is sized against — the single largest-weight leg de-risking/re-risking the China books.

**Why it's hard / why unfixed:** True publication dates drift month-to-month (NBS/PBoC 9th-15th, occasionally slipping); a fixed 22-trading-day shift is systematically too short when stamped at month-start, and a proper fix needs a per-print publication-date calendar mofcom doesn't serve. The leak is ~10 days at monthly frequency, hiding inside monthly-bar noise, and prior PIT audits focused on the US stack.

**Deep-reasoning brief:** Core tension: the highest-weight leg of a leveraged real-money book is validated on data it saw before the market did. Attack: design a publication-date-aware stamping for China credit (and a robust way to estimate release dates without a served calendar) and re-measure the credit leg's timing edge on the de-leaked series. A novel solution must tell a leveraged-China trader how much of the credit leg's edge survives once it can only act after the print was actually released.

### #28. anticipation.py net-liquidity leg subtracts billions from trillions — WALCL contribution numerically annihilated, so 'net liquidity velocity' is really just -RRP velocity

`dashboard` · `data-accuracy` · **severity: high** · confidence: high

**Evidence:** anticipation.py:103 netliq = R(WALCL)/1e6 - R(RRPONTSYD): WALCL=6,735,645 → /1e6 = 6.74 (trillions) but RRPONTSYD=26.9 left in billions — different units, and TGA dropped entirely. The canonical inputs.py:279 is walcl_bn - rrp_bn - tga_bn (all billions). m_netliq_vel = -slope_z(netliq.diff()): WALCL's trillion-scale daily change is ~0.001-0.01, RRP's is 1-50, so velocity is entirely -RRP momentum with the balance-sheet trend invisible. Feeds build_discovery, build_baskets, name/index_direction_phase0 outcome-cone / macro-stress overlays.

**Why it matters:** A leg labeled 'net liquidity velocity' — a headline liquidity-regime input to many decision-adjacent surfaces — is silently a pure -RRP-velocity signal; the Fed balance-sheet trend it purports to capture contributes zero, so any calibration that trusted it as 'net liquidity' is measuring the wrong thing.

**Why it's hard / why unfixed:** A silent units mismatch that produces plausible finite z-scores (slope_z normalizes scale so nothing NaNs), dating to the original engine commit so it has 'worked' the whole history; further masked because the leg is gated and the overlay is documented display/risk-only, so a direction audit wouldn't catch it.

**Deep-reasoning brief:** Core tension: a units bug that never crashes because normalization hides it, silently reducing a flagship liquidity leg to one of its three components. Attack: unify net-liquidity on the canonical 3-term billions definition across all engines, and add invariants/tests that would catch a mixed-unit subtraction producing a plausible-but-wrong z-score. A novel solution must ensure every 'net liquidity' consumer actually reflects the balance-sheet trend, and that a scale mismatch fails loudly rather than degrading into a single-component proxy.

### #29. GEX dealer-gamma sign is an unobservable assumption giving SPY/SPX opposite regimes and constant single-name regimes, feeding the vol-shock predictor's heaviest factor

`dashboard` · `engine-correctness` · **severity: high** · confidence: high

**Evidence:** gex_engine.py:53 signs GEX via sgn=where(is_call,1,-1) — the unobservable long-call/short-put dealer assumption. Cboe data: SPY 14 short/3 long vs SPX 11 long/6 short over the same 17 days; AAPL 17 long/0 short, IWM 17 short/0 long — single-name regimes are constant product attributes, not time-varying signals. gex.html shows 'short gamma' for SPY and 'long gamma' for SPX same day; vol_shock_scorecard _f_dealer_gamma (weight 1.0) inherits whichever product resolves (defaults SPX). The GEX forward-RV validator (gate.json) can never fill the minority-regime bucket (MIN_PER_BUCKET=30) for constant-regime names, so 'building history' is permanent not pending. vol_shock log has 3 rows all hit=null with a 'LEADING precursor' claim n=0.

**Why it matters:** Users see contradictory gamma regimes for the same index on the same day; single-name gex_confirm carries no forward information (permanent product attribute); the vol-shock predictor's heaviest factor inherits an unvalidated assumption-signed regime; and the validator structurally cannot ever bless most single names, giving a false 'will eventually validate' impression.

**Why it's hard / why unfixed:** True dealer sign is unobservable from Cboe OI alone (needs paid signed trade-level data); reconciling SPY vs SPX requires deciding which product's regime is canonical for US equity vol; and index minority buckets would need ~5+ years to reach n=30. The code is honest about the assumption in docstrings but doesn't surface or resolve the same-underlying divergence.

**Deep-reasoning brief:** Core tension: a regime whose sign is assumed, not observed, so it contradicts itself across products and is constant per single name — yet drives the top vol-shock factor. Attack: design a dealer-gamma read (or an honest confidence/abstention) that reconciles SPY vs SPX, exposes when the sign is assumption-driven vs inferable, and stops single-name GEX from posing as a time-varying signal it structurally can't be. A novel solution must either extract genuine time-varying signal or clearly demote the constant/contradictory cases so a real-money vol-shock reader isn't misled.

### #30. Regime-state caution haircut and crowding trim persistently cut real allocation using channels the engines' own OOS gates grade as non-additive / non-predictive

`dashboard` · `backtest-rigor` · **severity: high** · confidence: high

**Evidence:** basket_overlay_gate.json: live_overlay_helps=false, regime_marginal_over_voltarget=false, beats_brake=false — the L2 regime-caution leg failed its additive-value test vs mechanical vol-targeting, yet theme_scoring.py:595-599 and cycles.py:1151 apply the state-based haircut (0.85/0.70) unconditionally; only the scored deepener is gated on the verdict, no consumer reads live_overlay_helps. theme_crowding module header states basket-aggregate extension has NO forward-drawdown edge (Spearman ~0.07 on 27y) yet narrative_rotation.py:494-500 trims weight to cash for any crowding_z>0 (centered ~0, so ~half of held themes trimmed every run) and never redistributes — a persistent one-way exposure drag. Both calibrations transfer from an 11-SPDR proxy universe, not the thematic baskets actually trimmed.

**Why it matters:** Real basket gross and enter/accumulate→hold decisions are cut every run by two channels that already failed their own additive-value / edge gates, violating the validate-before-weight firewall the engine claims — the regime-caution leg the repo's own LOO-robust 1993-2026 study says adds nothing, and a crowding trim the code labels display-only/non-predictive that only ever reduces market exposure.

**Why it's hard / why unfixed:** The always-on mechanical vol-target (legitimately useful) and the failed regime-caution leg share one sizing_overlay() call, so separating them requires threading the gate verdict through; the per-name-vs-per-basket crowding distinction is subtle (crowding predicts single-name but diversifies away at basket level); and 'asymmetric down-size' framing launders a null signal into a prudent-sounding control.

**Deep-reasoning brief:** Core tension: two allocation cuts that fire every run are driven by channels the system's own OOS verdicts reject, wrapped in prudent-sounding 'caution/asymmetric' framing. Attack: separate the validated mechanical vol-target from the failed regime-caution and null crowding legs so only the gate-passing component binds sizing, and prove (on the actual thematic baskets, not the SPDR proxy) whether the trims are net-positive or a persistent drag. A novel solution must enforce validate-before-weight for these persistent cuts and stop laundering a null signal into a one-way exposure reduction.

### #31. Attribution/heavyweight/net_exposure and other complete engines are orphaned or false-documented; doctrine D1/D2/D4 vetoes fire as advisory flags — the safety/accountability surface looks operational but isn't

`bot + dashboard` · `engine-correctness` · **severity: high** · confidence: high

**Evidence:** attribution.persist has zero callers (data/brain/attribution/ absent; rollup permanently {} so the reputation damper can never trigger). heavyweight_outcomes.py has zero consumers and a false docstring claiming 'bot/heavyweight.py calls grade() each run' (it doesn't) — the heavyweight book's sizing-skill accountability is dead. DOCTRINE.md L131-138 specifies D1/D2/D4 as 'hard veto on bot's own sizing' but detectors.py hardcodes severity='flag'; phase2.py computes _d124_fired then only logs — nothing subtracts weight, so a buy into an extended name (D2) or adding to a diverging loser (D4) is detected and bought anyway. panel.adjudicate is imported but never called (dead second adjudicator).

**Why it matters:** The failure-mode detectors positioned as what 'would have prevented the 100%-concentration blowup' are inert display flags on the bot's own book; the accountability engine that would grade heavyweight sizing skill and feed it back to the Brain is dead with a docstring that actively misleads auditors; and the reputation damper's substrate never populates — the whole safety/accountability surface reads as done while gating nothing.

**Why it's hard / why unfixed:** Each module is complete, imports cleanly, mirrors a working sibling, and degrades-never-raises, so it passes any static review and CI is green; the gaps are single missing call sites / one-word severities discoverable only by cross-referencing consumer lists, and D1/D2/D4 target hard-to-observe intent (message tone, intent-to-average) so the authors downgraded them without documenting the drift from DOCTRINE.md.

**Deep-reasoning brief:** Core tension: a safety and accountability layer that is fully built, cleanly importing, and completely inert — with docstrings that assert integration that doesn't exist. Attack: design a liveness/wiring audit (and a doctrine-vs-code parity check) that makes an orphaned engine, an uncalled persist(), a false 'calls grade() each run' claim, or a spec'd-veto-that-only-flags fail loudly. A novel solution must guarantee that a component the operator believes is protecting a real-money book is actually invoked and actually binds, and that DOCTRINE and code can't silently drift.

### #32. Quality gate and regime history can't audit degradation: staleness is soft-flag only (total outage passes n_failed=0) and per-component freshness columns are deliberately stripped

`dashboard` · `backtest-rigor` · **severity: high** · confidence: high

**Evidence:** audit_macro.py:165-174 _check_stale calls flag() never fail(); collect.py aborts only at fail_pct>5%; a FRED breaker-skip leaves the parquet frozen and passes with n_failed=0. run.py:75-80 strips all c_ columns before persisting regime_history (confirmed: 0 c_ columns), storing growth_n_components but no flag distinguishing a live print from a 59-day ffill. Half-open breaker (base.py:147) leaves stale parquet live; global_liquidity.py:60,74 unbounded .ffill() propagates a frozen balance sheet forward as a live liquidity signal into the equity-allocation overlay. EBP (61d, past 45d ffill) silently exits recession_risk with the exported field null and no flag.

**Why it matters:** The end-of-collect gate presented as a safety net cannot block a render on feed staleness (a total FRED outage passes silently and the render commits a fresh-dated site on frozen inputs), and historical regime calls the bot traded on / the ledgers graded can't be audited for full-data vs degraded days — so every walk-forward silently mixes full-fidelity and price-only-proxy sessions and treats them identically, overstating the regime's fundamental grounding.

**Why it's hard / why unfixed:** Distinguishing legitimately-slow series (quarterly GDP ffill 95d, FOMC dot 400d) from a dead feed needs cadence-aware per-feed rules and a feed→decision dependency graph that doesn't exist; retro-reconstruction of freshness is impossible because c_ columns were dropped (for parquet size) before this bug class was known; and staleness was made non-fatal deliberately to avoid false CI aborts on late government prints.

**Deep-reasoning brief:** Core tension: the gate and the history that should let you audit degradation are the exact places freshness information is discarded, so an outage is invisible both live and in hindsight. Attack: design a cadence-aware feed-freshness gate that can block a render on a genuine outage (not on benign slow prints) and a point-in-time freshness ledger persisted alongside regime history so any backtested regime call is auditable for full-data vs degraded provenance. A novel solution must make 'this regime call was made on price-only proxies' both preventable live and visible forever after.

### #33. spvector LLM knife-veto is structurally unreachable and catalyst_tone event digest is non-deterministic — the advertised LLM safety layer can never fire, and would be a coin-flip if it did

`dashboard + cross-system` · `engine-correctness` · **severity: high** · confidence: high

**Evidence:** build_spvector.py:259 calls context_snapshot() with default on_stress_day=False, so event_snapshot() is skipped and the FOMC digest (always shock_reversible='unknown') is used; the veto branch needs sr=='persistent'. overlay_log.jsonl has 202 rows, every one shock_reversible='unknown', veto=False — zero vetoes ever, and the log can never accrue positive evidence for the veto's precision. If it WERE wired: catalyst_tone _call_model passes no temperature/seed and the event path fetches live shifting GDELT headlines with no caching, so the same dislocation day can yield 'persistent' on one run and 'reversible' on another. This non-determinism is systemic — master_brain/regime_snap_veto/desk producers all share the seedless client, so every graded LLM lean measures sampling noise.

**Why it matters:** The dashboard surfaces an 'LLM knife-veto active' safety UI and a live recommendation implying LLM oversight on the highest-stakes capitulation/washout-redeploy days, but the veto can never fire and the mechanical weight is always final; wiring it would make the trigger a non-reproducible LLM coin-flip exactly where being wrong is most expensive, and every self-scoring LLM ledger elsewhere is polluted by the same run-to-run variance.

**Why it's hard / why unfixed:** Wiring on_stress_day needs a stress classifier the veto path lacks, and the deeper question — whether a non-deterministic LLM read should flip a live equity weight on the worst days — was deliberately deferred to a log that can't accrue; DeepSeek/Anthropic determinism is weak even at temperature=0, GDELT headline sets shift intraday so the input itself is unstable, and the FOMC document-caching fix doesn't transfer to live headlines.

**Deep-reasoning brief:** Core tension: an advertised LLM safety layer that is disconnected, whose log can never earn trust, and whose trigger — if connected — would be non-reproducible on exactly the days it matters most. Attack: decide and design whether a non-deterministic LLM classification may ever move a live equity weight, and if so how to bound its variance (caching, ensembling, abstention, determinism) so the veto is reproducible; if not, replace the dead veto with something that can actually fire and accrue precision. A novel solution must make the LLM oversight the UI claims either real-and-reproducible or honestly absent, and stop seedless sampling noise from polluting graded ledgers.

### #34. Recommendation cards contradict their own guards side-by-side: BTC vector 'ACCUMULATE 55-100%' prints below a 0% midterm-blackout chip because recommend() has no blackout guard

`dashboard` · `confluence-gap` · **severity: high** · confidence: high

**Evidence:** vector.html.j2:454 renders {% if rec and rec.ok %} with no midterm guard, directly below the model-allocation chip (line 449) showing 0% when midterm.active; vector_allocation.html.j2:149 correctly guards with 'and not (midterm and midterm.active)', proving suppression was intended. build_vector.py:2396 calls btc_recommend.recommend() without passing midterm state, so it computes full exposure bands as if the blackout doesn't exist. Related: btc_cycle_thesis accumulate/breaking flags render at alert level on an n=3 in-sample 2-param cycle clock.

**Why it matters:** During the live 2026 midterm blackout the overview page prints 'ACCUMULATE · HIGH conviction · target 55-100% BTC' immediately below a 0%-cash chip — two decision-driving cards side-by-side with irreconcilable outputs, and a user reading the recommendation card risks acting on the suppressed-elsewhere signal.

**Why it's hard / why unfixed:** recommend() is a pure function deliberately kept ignorant of allocation-grid overlays; the blackout was bolted on as a final word in allocation() only, and the guard was applied to one template but not the other, so the pages diverged silently — reconciling requires threading the gate state into the decision layer or enforcing a consistent guard.

**Deep-reasoning brief:** Core tension: a pure recommendation function that doesn't know about the overlay that overrides it, guarded on one surface but not the other. Attack: design a single reconciled decision layer (or an enforced shared guard) so a blackout/override can never coexist with a contradicting accumulate recommendation on the same page. A novel solution must guarantee the two cards a trader reads always agree, without duplicating guard logic that can drift.

### #35. master_brain stacks correlated same-tape signals as independent confirmations, and 'display-only' cross_asset_confirm/RORO leans are fed to the decision LLM without lead/lag nuance

`dashboard` · `signal-quality` · **severity: medium** · confidence: medium

**Evidence:** gather_state assembles bonds, cross_asset_confirm, rate_inflation_transmission, btc, forex, entry_quality_breadth — all derived from overlapping latest.json; _macro_risk_posture and entry_quality_breadth both read the same macro label/liquidity_overlay; the per-field manual exclusion in bonds doesn't scale. cross_asset_confirm.py:23,313 declares 'DISPLAY-ONLY — nothing scored consumes this' but builds a to_brain dict (verdict, caution votes, fx_risk) that master_brain.py:513-522 ingests as the 'LEADING-FAMILY cross-check', forwarding coincident/fragility gauges (MOVE-vs-VIX, dollar-smile, EM-FX) without their per-leg lead/lag. RORO averages one momentum-z (DXY 20d) with six level-z legs at equal weight (no forward-IC) and its risk-on/off label flows to the brain.

**Why it matters:** The LLM synthesis receives multiple correlated confirmations reading as independent, so a single root cause (e.g. liquidity contraction) appears as cross-asset consensus through 4-5 sub-engines, inflating apparent conviction in the daily narrative users act on; and coincident/fragility gauges are laundered into the brain as a leading cross-check.

**Why it's hard / why unfixed:** Covariance over sub-engine outputs is never computed and structural decorrelation needs explicit factor attribution the architecture lacks; whether an LLM-context feed counts as 'scored' is genuinely ambiguous, and validating the brain's sensitivity to these inputs is hard without an outcome ledger on brain calls (which is itself polluted by the seedless-LLM problem).

**Deep-reasoning brief:** Core tension: 'independent confirmation' assembled from sub-engines that share a tape, plus display-only gauges quietly reaching the decision LLM. Attack: design a decorrelation/factor-attribution layer so the brain sees genuinely orthogonal evidence (or an honest correlation-adjusted conviction), and a principled boundary for what 'display-only' inputs may reach the LLM and with what lead/lag labeling. A novel solution must stop one root cause masquerading as multi-engine consensus in the narrative a trader acts on.

### #36. Anti-chase extension demote and other China board reorders run live on 2 days of unvalidated ledger; FRESH_TICKS and CN blend constants are anecdote-picked

`dashboard` · `predictive-power` · **severity: medium** · confidence: medium

**Evidence:** china_standout_track.py:15-18 states the board-order ledger is 'the honest prerequisite' before promoting the anti-chase DEMOTE, requiring n>=8/horizon, but board.parquet has 120 rows across only 2 dates (2026-06-30/07-01) while build_china_library.py:1065 already applies EXT_PENALTY=0.5 demoting extended names in the live blend. FRESH_TICKS=2 is justified by two named cases (HON/LOW); WASHOUT_BONUS/EXT_PENALTY/CN_TIER_FRAC/CN_WN_FLOOR set by narrative ('~one tier', 'MILD near-parity') with no sweep. FRESH_TICKS is the single knob defining 'buyable now' for every market.

**Why it matters:** A soft veto already reordering the China buy board (moving extended names ~one tier down) on an unproven anti-chase premise that won't validate for weeks-to-months — if A-share continuation is real on short horizons the demote actively hurts the ranking the user trades now — and the most decision-critical freshness/blend knobs rest on two-name anecdotes, so stale risen-already names can surface as fresh BUYs.

**Why it's hard / why unfixed:** Soft-demote reads as prudent risk management rather than a live bet, obscuring that it changes real board order; a defensible sweep needs the stop-out-vs-lead harness that exists for tier weights but was never re-run for this layer; and the two-name endorsement gives false confidence the knob was empirically tuned.

**Deep-reasoning brief:** Core tension: live board reorders and the master 'buyable now' knob are set by anecdote and shipped ahead of their own validation ledger. Attack: run the stop-out-vs-lead sweep for the freshness window and CN blend constants on held-out names, and make the anti-chase demote's live magnitude contingent on its ledger actually showing extended names underperform. A novel solution must ensure a real-money board reorder is either validated or clearly provisional, and that 'fresh' is calibrated rather than endorsed from two cases.

### #37. China Mastermind leveraged GTAA books advertise concrete Sharpe/drawdown edge on admittedly uncalibrated hand-set prior weights

`dashboard` · `backtest-rigor` · **severity: medium** · confidence: medium

**Evidence:** china_masterminds.py:30-33 docstring: 'DISPLAY-ONLY / experimental … PRIORS-based knobs (calibration is a fast-follow)', yet PROFILES blurbs assert 'several times the index's Sharpe at well under half its worst drawdown' and 'out-compound CSI 300'. W_TREND/W_CARRY/W_REGIME/W_XMOM=0.30/0.15/0.40/0.15 and STRUCT_CARRY tilts are hand-set, not fit; backtest() runs split_half_oos on these priors and levers to 1.8x over a short (~2013+, ~1.5 boom-bust) A-share sample. tsmom_alloc feeding conviction weights also aligns CN/HK closes to the US calendar with no session-lag correction.

**Why it matters:** Per-profile flagship pages present Sharpe/drawdown/OOS panels that read as validated but the weights were never calibrated; split_half_oos on hand-tuned priors over one short regime-poor sample is weak evidence, and at 1.8x leverage any overfit in the credit/regime weights is magnified — a user could size real capital to an 'edge' that is a prior, not a measurement.

**Why it's hard / why unfixed:** Calibrating six-asset conviction weights on short regime-poor A-share history without overfitting is genuinely hard, so the fast-follow stays deferred; the honest docstring coexists uneasily with confident blurbs in the same file, and there is no single global clock to fix the CN/HK-vs-US session alignment without shrinking overlapping history.

**Deep-reasoning brief:** Core tension: a leveraged book whose knobs are admitted priors while its marketing quotes concrete Sharpe/drawdown edge. Attack: design a calibration (or an honest uncertainty-banded presentation) for six-asset conviction weights on short, regime-poor, session-misaligned A-share data that neither overfits nor advertises unearned edge, and correct the cross-session as-of alignment feeding conviction. A novel solution must make the advertised edge either measured with honest CIs or clearly labeled as a prior a leveraged trader should not size against.

### #38. Autonomous ungated-Opus book runs on schedule and is risk-blind by default while disciplined flagship seats default OFF; bandit ranks by hit-rate not EV

`bot` · `predictive-power` · **severity: medium** · confidence: medium

**Evidence:** autonomous.py:5-11 'no gate, no research paper, NO committee' yet overnight.py schedules it and calibration.py:546 grades it as a first-class seat on the same scale as the gated flagship. _regime_brief returns only quad_name+liquidity; risk_lens.briefing is gated behind MASTERMIND_RISK_GOVERNOR (default OFF) so the LLM narrative path gets none of the fused risk verdict/drivers by default (the deterministic phase2 gate still reads full regime). MASTERMIND_FLAGSHIP_JUDGMENT defaults OFF. bandit.py:92-104 ranks policies by binary hit (realized>=-0.05) not avg_rel_return, so a many-small-wins/occasional-big-loss negative-EV policy ranks near-optimal and diverges from the return leaderboard.

**Why it matters:** A scheduled ungated free-discretion Opus book can hold positions contradicting the gated flagship with no reconciliation, is graded on the same leaderboard (a lucky autonomous streak compared directly to disciplined results), reasons about allocation without the dashboard's fused risk drivers by default (can lean bullish on an elevated-drawdown day), and a hit-rate bandit would select the worst compounder if ever used to switch policy.

**Why it's hard / why unfixed:** Whether judgment flags are ON is an environment/deploy fact not in the committed repo; grading ungated discretion fairly against a gated book is a known-hard attribution problem; the governor-OFF default preserves byte-identical builds; and a return-weighted bandit needs a continuous-reward posterior that converges slowly on small resolved-thesis counts.

**Deep-reasoning brief:** Core tension: an ungated, risk-blind, hit-rate-ranked discretionary book graded head-to-head against a disciplined gated one. Attack: design fair cross-book attribution (so discipline isn't penalized by a lucky ungated streak), give the autonomous LLM the fused risk verdict by default without breaking reproducibility, and rank policies by expected value not binary hit-rate. A novel solution must make the leaderboard comparison meaningful and stop the autonomous book from reasoning risk-blind on real paper money.

### #39. Live recession/nowcast and business-cycle signals read latest-revised FRED and run at a lag the calibration wasn't fit for; the collected ALFRED store is unused on the live path

`dashboard` · `data-accuracy` · **severity: medium** · confidence: medium

**Evidence:** conditions.py builds claims_yoy/recession_risk/sticky-CPI off latest-revised _col(f,...); grep 'fred_vintage' in engine/ returns nothing though vintages.parquet exists. recession_risk feeds drawdown_risk whose >=80 → ~45% forward-dd hit-rate was measured on the same revised data (meaningless as PIT) and on a recession_risk composition that included Sahm before claims (weight 1.0) hard-replaced it. business_cycle runs live at lag_m=0 but its roc_threshold=-1.25 and '5.7-month lead / 3 FP' honesty stats were calibrated at lag_m=1 (validate_business_cycle default --lag-months=1). Only ~3 endogenous PIT-era recessions exist.

**Why it matters:** The claimed forward-drawdown and lead-time edges that users and the brain see were measured on a data frame (revised, differently-composed, differently-lagged) that the live signal does not fire on, so the shipped honesty numbers overstate the live signal's behavior — and this inflation propagates into the macro-stress sector penalty and the brain's regime framing.

**Why it's hard / why unfixed:** Wiring PIT vintages into the live feature frame needs an as-of join per revision-prone series plus re-fitting every downstream threshold; the base-effect inflation series are absent from the store; and with only ~3 PIT-era recessions any re-fit is severely sample-starved — there is no clean answer, only a documented tradeoff between timeliness and honesty.

**Deep-reasoning brief:** Core tension: recession/cycle signals whose advertised lead-time and hit-rate were fit on a different data frame than the one they fire on live. Attack: reconcile the live path with its calibration — either move the live signal onto the calibrated frame (PIT vintages, matched lag, matched composition) or re-calibrate honestly at the live configuration, quantifying the sample-starvation uncertainty. A novel solution must make the '45% forward-dd / 5.7-month lead' numbers a trader reads actually describe the signal that fires today.

### #40. Sector-heat macro penalty uses a static hand-pasted beta table (XLC=1.0 predates XLC) while the data-derived per-channel IC overlay that could correct it is kept display-only

`dashboard` · `confluence-gap` · **severity: medium** · confidence: medium

**Evidence:** playbook.py:590-592 computes heat via sector_macro_beta reading config.yml's hand-pasted table (calibrate_macro_betas.py:16 'OFFLINE ONLY … pasted into config.yml, never recomputed'); the measured per-sector rate/inflation forward-IC overlay (sector_rate_inflation.py) is imported at playbook.py:574 but explicitly kept 'DISPLAY-ONLY context, never part of the heat score'. XLC=1.0 predates XLC's 2018 launch so it is a pure textbook prior penalizing Communications heat as hard as Financials.

**Why it matters:** The same concept — how much macro risk should penalize a sector — is computed two divergent ways: a coarse hand-pasted prior drives the score and sizing while the data-derived read that would correct XLK rate-sensitivity and XLU/XLRE bond-proxy behavior is shown but ignored, and a textbook prior masquerades as a measurement in the live sizing path.

**Why it's hard / why unfixed:** Folding the measured IC in requires reconciling two estimators (conditional-drawdown beta vs forward-IC) onto one scale, and the transmission calibration itself found no rate/inflation leg robust enough to time returns — so promoting it risks importing noise; the safe-but-stale choice was deliberate.

**Deep-reasoning brief:** Core tension: a decision-driving macro penalty runs on a hand-pasted prior (some entries physically impossible) while the measured correction is quarantined as display-only because it's noisy. Attack: design a principled reconciliation of the textbook-prior beta and the data-derived forward-IC so the sizing penalty reflects measured sector-macro sensitivity where it's reliable and shrinks to prior where it isn't. A novel solution must retire impossible priors (XLC pre-2018) from real-money sizing without importing the transmission read's noise wholesale.

### #41. Calibration Hub / desk cards display conviction badges with n=0 measured basis; foresight score is hardcoded magic-number tables; anticipation GO-gate is a frozen self-certifying artifact

`dashboard` · `confluence-gap` · **severity: medium** · confidence: high

**Evidence:** calibration_hub _MIN_SAMPLE=10 correctly labels desks 'cold' but the underlying leans (altdata 120 open, stock_desk 75 open) are still surfaced as accountable directional calls with conviction labels that have no measured basis, and no UI mechanism stops cold desks showing conviction on non-calibration pages. foresight_score.py:104-130 is entirely hardcoded lookup tables (0.85/0.4/0.5, 0.9/0.6/0.45, magic 0.4 placeholder) with no IC — quarantined display-only but shows a precise 0-100 score. anticipation.py's GO/NEUTRAL gate is loaded from a frozen anticipation_gate.json last changed at #257; anticipation_phase0.py that computes it is wired into no pipeline and never re-runs, with a stale n_rows=1175398 stamp and no freshness marker.

**Why it matters:** Precise-looking conviction badges and 0-100 scores invite over-trust when their basis is n=0 or unfitted constants, and a self-certifying 'Phase-0 measured' badge on a gate that never refreshes can keep firing a decayed leg as validated — the same stale-certification pattern that makes a decayed signal indistinguishable from a current one.

**Why it's hard / why unfixed:** The badges are genuinely time-gated (horizons can't mature for months) and the foresight inputs are LLM/narrative categoricals with tiny samples and no clean forward label, so proper calibration is hard and display-only is the right home — but there is no freshness/expiry marker or UI guard preventing a stale or unfitted number from reading as validated.

**Deep-reasoning brief:** Core tension: precise, validated-looking numbers (conviction badges, 0-100 foresight, 'Phase-0 measured' gates) whose basis is absent, unfitted, or frozen — indistinguishable from earned ones. Attack: design a freshness/basis-provenance marker and UI contract so any displayed conviction/score carries an honest 'n=0 / unfitted / last-validated' label and a stale calibration gate can't self-certify as current. A novel solution must let a trader instantly tell an earned conviction from a hand-set prior or a decayed certification.

### #42. entered_book/left_book and other rotation events fire at hardcoded 'high' severity from a rank ordering with documented ~0 IC, degrading the whole Alert Center's signal-to-noise

`dashboard` · `confluence-gap` · **severity: medium** · confidence: medium

**Evidence:** allocation_alerts.py:86-98 hardcodes severity='high' for entered_book/left_book flowing into the site-wide Alert Center as 'rotation', while the same module docstring says 'Display-only: the playbook is discipline, not a prediction' and narrative_rotation states theme momentum has 'rank-IC ~0 on the unbiased universe' (baskets_calibration proxy rank_ic -0.0295/-0.041). Severity is hardcoded per event-type; the aggregator has no notion of the emitter's measured IC, so 'directional:False' in the engine and 'severity:high' in the alert are disconnected.

**Why it matters:** A low-turnover artifact of a null-edge momentum ordering is tagged 'high' in the cross-engine triage center alongside validated risk-off signals, inflating a null event to the same priority as genuine alerts and degrading signal-to-noise for the whole Alert Center where the user triages.

**Why it's hard / why unfixed:** The alert layer has no channel to consume per-engine validation verdicts, so reconciling emitter IC with alert severity requires a feedback loop that doesn't exist; and severity is set at emission per event-type with no IC awareness.

**Deep-reasoning brief:** Core tension: a triage center that ranks a documented-null-edge rotation event as high as a validated risk-off signal because severity is hardcoded and disconnected from measured IC. Attack: design a severity model where an emitter's measured IC/validation verdict flows into the alert priority, so null-edge display events can't crowd out genuine signals. A novel solution must protect the Alert Center's signal-to-noise by making severity reflect measured edge, not the event type.

### #43. Analyst-revision convergence channel uses the consensus LEVEL the repo's own revision engine calls near-useless; whitehouse_brain names beneficiary tickers with no existence/citation gate

`dashboard` · `confluence-gap` · **severity: medium** · confidence: medium

**Evidence:** analyst_revisions.py:4-7 states the level 'is near-useless and optimism-skewed … we score the DELTA, never the level', yet altdata.py:281-300 gates the analyst_upgrade_cluster convergence channel (weight 0.35) on a LEVEL threshold (bull>=0.6 AND rising), and analyst_revisions feeds only the display panel. Separately, whitehouse_brain.py:282-302 validates beneficiary tickers only by symbol shape + dedup, reusing catalyst_tone's _extract_json but NOT its _verify_citations/confidence-floor, so a hallucinated/delisted/misidentified ticker can reach the site-wide banner on every page with only the prompt 'name real tickers you are confident exist' as a guard.

**Why it matters:** The convergence path wires in the exact discredited level construction the house literature rejects (a user relying on 'analyst upgrades' gets the near-useless version), and the highest-visibility surface in the product (the every-page banner) can show a wrong or non-existent ticker, doing trust damage disproportionate to the advisory nature on a site claiming institutional signal quality.

**Why it's hard / why unfixed:** Replacing the level channel with the revision delta changes firing semantics and re-tunes a weight against a channel-level track record that doesn't exist; and policy-to-ticker reasoning is inherently generative with no source substring to verify against, so the citation trick doesn't transfer — a price-store existence check catches dead names but not wrong-sector misattributions.

**Deep-reasoning brief:** Core tension: the same concept computed two ways where the discredited version is the one wired to decisions, and a generative ticker-naming step feeding the most-visible surface with no existence/plausibility gate. Attack: route the convergence channel to the validated revision-delta construction, and design an existence + plausibility gate for LLM-named beneficiary tickers (universe membership, sector-consistency) that degrades to abstention rather than a wrong chip. A novel solution must stop the discredited level signal from posing as convergence edge and stop a hallucinated ticker from ever reaching the every-page banner.

### #44. Alpha-weight basket overlay applies today's momentum ranking across all history (undisclosed look-ahead flattery of the tilt)

`dashboard` · `data-accuracy` · **severity: medium** · confidence: medium

**Evidence:** basket_index.py:_base_weights mode=='alpha' (167-180) computes a single static weight vector from the last 120 days as-of-today, z-scores it, and consolidated_candle applies that static vector to ALL historical dates via daily renormalization; weight_variants renders the resulting 'alpha' close for the entire series. The docstring calls it 'display-only … how a conviction/alpha-tilt reshapes the same basket' but does not disclose the look-ahead.

**Why it matters:** The alpha overlay curve over-weights names that are momentum leaders as of TODAY across their entire past, so a user comparing equal-weight vs alpha sees an alpha curve biased upward by construction — a classic look-ahead flattery presented without disclosure.

**Why it's hard / why unfixed:** Making it point-in-time converts a cheap single-pass reweight into a full rolling backtest (rolling the 120d strength weights daily through history); the static tilt was a deliberate display shortcut, but the look-ahead is undisclosed on the card.

**Deep-reasoning brief:** Core tension: a 'how a tilt would have reshaped this basket' curve that uses today's winners to reweight all of history, shown without disclosure. Attack: either make the alpha overlay point-in-time (rolling weights) or clearly disclose it as an in-sample illustration, so the comparison a user draws isn't structurally flattering. A novel solution must ensure any 'would-have' curve a trader compares against equal-weight is either honestly PIT or unambiguously labeled as look-ahead.

### #45. Confluence constants and confluence math are duplicated across three isolated repos with a Terminal MACRO_REPO path pointing at the non-worktree checkout — silent cross-repo drift with no behavioral parity test

`cross-system` · `integration` · **severity: medium** · confidence: medium

**Evidence:** confluence_tiers.py:32-35 (dashboard) and charting-app/signal_layer/confluence.py:37-48 (Terminal) independently re-declare RSI_LEN/FAST_LEN/BASE_LEN/SIG_LEN/CONF_W/BUY_RSI_MAX, with MACRO_REPO defaulting to the main checkout not the active worktree; golden_gate self-checks the oracle so it can't catch a constant drift; the tier cascade adds FRESH_TICKS/projections/not-topped logic beyond the oracle so a byte-parity gate can't cover it. hk_regime classify() calls hk_global.composite() without the as-of truncation that D80 added only to snapshot(), leaking future factor bars into historical/backfilled HK regime labels; derive_daily_close hard-defaults America/New_York for all regions so any CN/HK/CA intraday session is mis-bucketed on NY calendar days.

**Why it matters:** A drift in any constant, a Terminal pointed at a stale worktree, an untruncated HK backfill, or an NY-calendar mis-bucket of an Asia session all silently make one system's signal disagree with another's for the same symbol/date, with no behavioral contract test spanning the repos to catch it — a latent correctness landmine that widens as intraday and backfill coverage grows.

**Why it's hard / why unfixed:** No shared package exists across the three deliberately isolated repos and a byte-parity gate can't cover the extra cascade logic, so a behavioral contract test spanning repos is needed; the tz/truncation gaps are silent because the currently-fed universe (US intraday, live HK last-row) is correct under the defaults, so no test or output ever reveals them.

**Deep-reasoning brief:** Core tension: the same signal math lives in three isolated repos coupled only by copy-paste and hardcoded paths, with region/time-zone/as-of defaults that are correct only for today's narrow inputs. Attack: design a cross-repo behavioral parity contract (and region/tz/as-of-aware primitives) that catches constant drift, worktree-path mistakes, untruncated backfills, and calendar mis-bucketing before they diverge a real symbol's signal. A novel solution must guarantee one symbol's signal is identical across systems and correct for every region, not just US-live.

### #46. Backtest/track-record dividend-adjusted total-return bias and same-tape RORO/coincident labeling — bounded, documented, but consistently optimistic across every drawdown number

`dashboard` · `backtest-rigor` · **severity: medium** · confidence: medium

**Evidence:** track_record.py:19-27 documents that an interim dividend rebases the entry bar but not the t+H bar, so forward returns/drawdowns are total-return-with-hindsight (bounded <1%/60d), and the same back-adjusted series feeds sector_signals and meta_label with no equivalent caveat; forward drawdown magnitudes (the CHARTER §3 metric the buy-filter is graded on) are systematically nudged shallower and this compounds with the same-bar-entry bias. The OI leg (btc_leverage_cascade) is self-confessed anti-predictive (lift 0.36) yet surfaced as a de-risk warning; the tick-rule net-flow signed fields (net_sign_recovery 0.41, direction_reliable=false) remain emitted despite the signing gate being closed.

**Why it matters:** Every drawdown number in the track record is consistently biased in the optimistic direction (retroactive dividend credits soften troughs, compounding same-bar entry), and several display surfaces carry signed/anti-predictive fields the engines' own gates reject as unreliable — small individually but a persistent one-directional optimism across the artifacts a trader sizes against.

**Why it's hard / why unfixed:** Removing the dividend bias needs an unadjusted/as-of-adjusted second price store the free feed doesn't provide; the signed magnitude and direction share the same raw fields (net_premium is both), so suppressing direction without losing magnitude needs field-level reliability flags; and the anti-predictive OI leg's contrarian-vs-derisk reading is an unmade product decision.

**Deep-reasoning brief:** Core tension: bounded-but-consistent optimism baked into every drawdown metric, plus display fields the engines' own gates say are unreliable still emitted. Attack: design a return/drawdown convention that isolates price-return from total-return (or a principled haircut) and a field-level reliability contract so signed/anti-predictive fields can't be read directionally when their gate is closed. A novel solution must remove the one-directional optimism a trader would otherwise discount by guesswork, and stop rejected fields from leaking as signals.
